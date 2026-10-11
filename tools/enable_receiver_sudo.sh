#!/usr/bin/env bash
# Run once on laptop 10: sudo bash tools/enable_receiver_sudo.sh
# Grants only the receiver commands used by the current laboratory tests.
set -euo pipefail

if [[ ${EUID} -ne 0 || ${SUDO_USER:-} != csi ]]; then
    printf '%s\n' 'Run this script as csi with sudo on laptop 10.' >&2
    exit 1
fi
if [[ ! -d /sys/class/net/wlp2s0 ]]; then
    printf '%s\n' 'Expected laptop 10 interface wlp2s0 is absent.' >&2
    exit 1
fi
root_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)
expected_dir=$(getent passwd csi | cut -d: -f6)/ros2_ws/src/large_data_1009/ROSPacer
if [[ "$root_dir" != "$expected_dir" ]]; then
    printf '%s\n' "Expected checkout: $expected_dir" >&2
    exit 1
fi
mkdir -p -- "$root_dir/runs/sudo_setup"
candidate=$(mktemp "$root_dir/runs/sudo_setup/receiver.XXXXXX.sudoers")
cat > "$candidate" <<'POLICY'
# ROSPacer laptop 10: bounded receiver operations, no general root shell.
csi ALL=(root) NOPASSWD: /usr/bin/true, /usr/sbin/sysctl net.core.rmem_max, /usr/sbin/sysctl -w net.core.rmem_max=1048576, /usr/sbin/sysctl -w net.core.rmem_max=212992, /usr/sbin/iw dev wlp2s0 survey dump, /usr/sbin/iw dev wlp2s0 station dump
POLICY
/usr/sbin/visudo -cf "$candidate"
/usr/sbin/visudo -c
target=/etc/sudoers.d/rospacer-csi
if [[ -e "$target" || -L "$target" ]]; then
    if [[ ! -L "$target" ]] && cmp -s -- "$candidate" "$target"; then
        printf '%s\n' 'The same policy is already installed.'
        exit 0
    fi
    printf '%s\n' "Refusing to overwrite existing policy: $target" >&2
    exit 1
fi
install -o root -g root -m 0440 -- "$candidate" "$target"
if ! /usr/sbin/visudo -c; then
    # Only roll back the file just created by this invocation.
    rm -- "$target"
    printf '%s\n' 'Validation failed; the new policy was removed.' >&2
    exit 1
fi
printf '%s\n' 'Installed: limited passwordless receiver commands.'
printf '%s\n' 'No buffer value or network setting has been changed.'
