import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

import logging
logging.getLogger('matplotlib.font_manager').setLevel(logging.WARNING)

class FocusPlotter:
    def __init__(self):
        self.positions = []
        self.scores = []
        self.phase_changes = []     # List of (position, phase_name)
        self.servo_bumps = []       # List of motor positions when servo bump occurred

    def add_point(self, position, score):
        self.positions.append(position)
        self.scores.append(score)

    def mark_phase(self, position, phase_name):
        self.phase_changes.append((position, phase_name))

    def mark_servo_bump(self, position):
        self.servo_bumps.append(position)

    def save_graph(self, save_path):
        if not self.positions or not self.scores:
            return

        plt.style.use('seaborn-darkgrid')
        fig, ax = plt.subplots()
        ax.plot(self.positions, self.scores, 'b.-', label="Focus Score")

        # Highlight peak
        max_idx = self.scores.index(max(self.scores))
        peak_pos = self.positions[max_idx]
        peak_score = self.scores[max_idx]
        ax.plot(peak_pos, peak_score, 'ro', label=f"Peak: {peak_score:.2f}")
        ax.annotate(f"Peak\n{peak_score:.2f}", xy=(peak_pos, peak_score),
                    xytext=(peak_pos, peak_score + 5),
                    arrowprops=dict(arrowstyle='->', color='red'))

        # Add phase change markers
        for pos, label in self.phase_changes:
            ax.axvline(x=pos, color='gray', linestyle='--', alpha=0.5)
            ax.text(pos, ax.get_ylim()[1]*0.95, label, rotation=90, va='top', ha='right', fontsize=8)

        # Add servo bump markers
        for pos in self.servo_bumps:
            ax.axvline(x=pos, color='orange', linestyle=':', alpha=0.5)
            ax.text(pos, ax.get_ylim()[1]*0.2, 'servo', rotation=90, va='top', ha='center', fontsize=7)

        ax.set_xlabel("Motor Position")
        ax.set_ylabel("Focus Score")
        ax.set_title("Focus Score vs Motor Position")
        ax.legend()
        fig.tight_layout()
        fig.savefig(save_path)
        plt.close(fig)

