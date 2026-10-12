"""Offline scientific plots of measured B2 receiver rates and burst timing."""
import json
from pathlib import Path
import statistics
import sys
from deploy import ROOT


def main():
    sys.path.insert(0, str(ROOT.parent/'tmp/w1_plotdeps'))
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib import pyplot as plt, font_manager
    font = Path('C:/Windows/Fonts/malgun.ttf')
    if font.exists():
        font_manager.fontManager.addfont(str(font))
        plt.rcParams['font.family'] = font_manager.FontProperties(fname=str(font)).get_name()
    plt.rcParams['axes.unicode_minus'] = False
    base = ROOT/'runs/w1_20261012_ch149/b2_fixedperiod'
    summary = json.loads((base/'summary.json').read_text())
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), layout='constrained')
    for name, color in [('clean_otherAP_idle', '#929aa4'), ('B2_1', '#3973b9'), ('B2_2', '#208070'), ('B2_3', '#ba7534')]:
        rows = json.loads((base/(name+'_10_server.json')).read_text())['intervals']
        x, y = [], []
        for interval in rows:
            streams = interval['streams']
            x.append((streams[0]['start']+streams[0]['end'])/2)
            y.append(sum(r['bytes'] for r in streams)*8/streams[0]['seconds']/1e6)
        axes[0].plot(x, y, color=color, label='AP2 유휴' if name.startswith('clean') else name, linewidth=1.7)
    axes[0].set(xlabel='각 run 수신 측 경과시간(s)', ylabel='UDP 수신 payload(Mb/s)', title='B2 · 1초 구간 수신 처리량', ylim=(0, 260))
    axes[0].legend(fontsize=9)
    bursts = summary['contender']['bursts']
    periods = [b['start_monotonic_s']-a['start_monotonic_s'] for a, b in zip(bursts, bursts[1:])]
    durations = [b['client_end']['streams'][0]['udp']['seconds'] for b in bursts]
    axes[1].plot(range(1, len(periods)+1), periods, 'o', ms=3, color='#3973b9', label='시작 간격')
    axes[1].plot(range(1, len(durations)+1), durations, '.', color='#208070', label='UDP 전송 길이')
    axes[1].axhline(4, color='#3973b9', alpha=.35, linestyle='--')
    axes[1].axhline(2, color='#208070', alpha=.35, linestyle='--')
    axes[1].set(xlabel='간섭 burst 번호', ylabel='시간(s)', title=f'실제 시작 간격 중앙값 {statistics.median(periods):.3f}s', ylim=(0, 5))
    axes[1].legend(fontsize=9)
    for ax in axes:
        ax.grid(axis='y', alpha=.2)
        ax.spines[['top', 'right']].set_visible(False)
    fig.savefig(base/'B2_measurements.png', dpi=170)
    fig.savefig(base/'B2_measurements.svg')
    plt.close(fig)
    print('B2 measured-rate and timing figures saved')


if __name__ == '__main__':
    main()
