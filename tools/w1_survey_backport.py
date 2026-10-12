"""Prepare the survey-channel fix against an exact Ubuntu mt76 source version.

This prepares source only. It never installs or reloads a kernel module.
The change backports the channel-context survey bookkeeping described at
https://marc.info/?l=linux-wireless&m=179080859630807&w=1
to Linux 6.8's main_chan field (newer kernels use main_chandef).
"""
import argparse
import difflib
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil


def apply_file_diff(root, chunk):
    lines = chunk.splitlines(keepends=True)
    rel = lines[1].split()[1].split('/drivers/net/wireless/mediatek/mt76/', 1)[1]
    target = root / rel
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError('diff escapes mt76 source')
    original = target.read_bytes().decode().splitlines(keepends=True) if target.exists() else []
    result, cursor, i = [], 0, 2
    while i < len(lines):
        match = re.match(r'@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@', lines[i])
        if not match:
            raise ValueError('expected hunk: ' + lines[i])
        old_start, old_count = int(match[1]), int(match[2] or 1)
        new_count = int(match[4] or 1)
        start = old_start - 1 if old_count else old_start
        if start < cursor:
            raise ValueError('overlapping hunk')
        result.extend(original[cursor:start])
        cursor, consumed, produced = start, 0, 0
        i += 1
        while i < len(lines) and not lines[i].startswith('@@ '):
            line = lines[i]
            if line.startswith('\\ No newline'):
                raise ValueError('unterminated line requires explicit handling')
            if line[0] in ' -':
                if cursor >= len(original) or original[cursor] != line[1:]:
                    raise ValueError(f'exact context mismatch: {rel}:{cursor+1}')
                cursor += 1
                consumed += 1
            if line[0] in ' +':
                result.append(line[1:])
                produced += 1
            i += 1
        if (consumed, produced) != (old_count, new_count):
            raise ValueError('hunk counts mismatch')
    result.extend(original[cursor:])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(''.join(result).encode())


def replace_once(root, name, old, new):
    path = root / name
    raw = path.read_bytes().decode()
    if raw.count(old) != 1:
        raise ValueError('unexpected source anchor: ' + name)
    path.write_bytes(raw.replace(old, new).encode())


def prepare(base, version):
    root = base / ('ubuntu_' + version) / 'mt76'
    if root.exists():
        raise ValueError('preserve existing prepared source: ' + str(root))
    shutil.copytree(base / 'pristine' / 'mt76', root)
    raw = gzip.decompress((base / f'linux-hwe-6.8_6.8.0-{version}.{version}~22.04.1.diff.gz').read_bytes()).decode()
    chunks = re.split(r'(?=^--- linux-hwe-6.8-6.8.0.orig/)', raw, flags=re.M)
    selected = [c for c in chunks if c.strip() and '/drivers/net/wireless/mediatek/mt76/' in c.splitlines()[0]]
    for chunk in selected:
        apply_file_diff(root, chunk)
    changed = ['mac80211.c', 'mt76.h', 'mt792x_core.c', 'mt7921/main.c']
    before = {n: (root / n).read_bytes().decode() for n in changed}
    replace_once(root, 'mac80211.c', 'void mt76_set_channel(struct mt76_phy *phy)\n',
                 '/* Backport: assign survey counters to the active channel context. */\n'
                 'void mt76_set_survey_channel(struct mt76_phy *phy,\n'
                 '\t\t\t     const struct cfg80211_chan_def *chandef)\n'
                 '{\n\tif (!chandef->chan)\n\t\treturn;\n\n'
                 '\tmt76_update_survey(phy);\n\tphy->chandef = *chandef;\n'
                 '\tphy->main_chan = chandef->chan;\n'
                 '\tphy->chan_state = mt76_channel_state(phy, chandef->chan);\n'
                 '}\nEXPORT_SYMBOL_GPL(mt76_set_survey_channel);\n\n'
                 'void mt76_set_channel(struct mt76_phy *phy)\n')
    replace_once(root, 'mt76.h', 'void mt76_update_survey(struct mt76_phy *phy);\n',
                 'void mt76_update_survey(struct mt76_phy *phy);\n'
                 'void mt76_set_survey_channel(struct mt76_phy *phy,\n'
                 '\t\t\t     const struct cfg80211_chan_def *chandef);\n')
    replace_once(root, 'mt792x_core.c', '\tmvif->mt76.ctx = ctx;\n',
                 '\tmvif->mt76.ctx = ctx;\n'
                 '\tmt76_set_survey_channel(&dev->mphy, &ctx->def);\n')
    old = '\tmt792x_mutex_acquire(phy->dev);\n\tieee80211_iterate_active_interfaces(phy->mt76->hw,\n'
    replace_once(root, 'mt7921/main.c', old,
                 '\tmt792x_mutex_acquire(phy->dev);\n'
                 '\tmt76_set_survey_channel(phy->mt76, &ctx->def);\n'
                 '\tieee80211_iterate_active_interfaces(phy->mt76->hw,\n')
    for name in ['mac80211.c', 'mt792x_core.c', 'mt7921/main.c']:
        path = root / name
        path.write_bytes(path.read_bytes() + b'\nMODULE_INFO(rospacer_survey_fix, "chanctx-6.8-v1");\n')
    patch = ''.join(''.join(difflib.unified_diff(before[n].splitlines(keepends=True),
                    (root/n).read_bytes().decode().splitlines(keepends=True),
                    fromfile='a/'+n, tofile='b/'+n)) for n in changed)
    (root.parent/'survey_backport.patch').write_bytes(patch.encode())
    # Build only the PCIe MT7921 dependency chain using the installed config.
    (root/'Kbuild').write_bytes(b'''obj-m += mt76.o mt76-connac-lib.o mt792x-lib.o
mt76-y := mmio.o util.o trace.o dma.o mac80211.o debugfs.o eeprom.o tx.o agg-rx.o mcu.o
mt76-$(CONFIG_PCI) += pci.o
mt76-$(CONFIG_NL80211_TESTMODE) += testmode.o
mt76-connac-lib-y := mt76_connac_mcu.o mt76_connac_mac.o mt76_connac3_mac.o
mt792x-lib-y := mt792x_core.o mt792x_mac.o mt792x_trace.o mt792x_debugfs.o mt792x_dma.o
mt792x-lib-$(CONFIG_ACPI) += mt792x_acpi_sar.o
CFLAGS_trace.o := -I$(src)
CFLAGS_mt792x_trace.o := -I$(src)
obj-m += mt7921/
''')
    (root/'mt7921/Kbuild').write_bytes(b'''obj-m += mt7921-common.o mt7921e.o
mt7921-common-y := mac.o mcu.o main.o init.o debugfs.o
mt7921-common-$(CONFIG_NL80211_TESTMODE) += testmode.o
mt7921e-y := pci.o pci_mac.o pci_mcu.o
''')
    files = {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in root.rglob('*') if p.is_file()}
    (root.parent/'source_manifest.json').write_text(json.dumps(files, indent=2))
    return {'version': version, 'ubuntu_file_diffs': len(selected), 'files': len(files), 'source': str(root)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--version', choices=['136', '138'], required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.source, args.version)))
