"""Draw the architecture and data-flow diagrams used by docs/22_Architecture_and_Data_Flow.md.

    python scripts/draw_diagrams.py        # writes docs/figures/architecture.png and docs/figures/dataflow.png

Needs matplotlib (experiments/requirements-experiments.txt). The Mermaid sources in the document render on GitHub without it.
"""
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / 'docs' / 'figures'
INK = '#1c2b3a'
COL = {'untrusted': '#fde8e4', 'boundary': '#fff3d6', 'trusted': '#e2f1ef', 'record': '#e7e9f7', 'model': '#f6e4f2', 'human': '#eef6dc'}
EDGE = {'untrusted': '#b54432', 'boundary': '#b07810', 'trusted': '#1b7f79', 'record': '#4b4b9a', 'model': '#9a4b8a', 'human': '#5a8a1f'}


def box(ax, x, y, w, h, text, kind, size=8.6, bold=False):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0.02,rounding_size=0.12', fc=COL[kind], ec=EDGE[kind], lw=1.4))
    ax.text(x + w / 2, y + h / 2, text, ha='center', va='center', fontsize=size, color=INK, fontweight='bold' if bold else 'normal',
            linespacing=1.25)


def zone(ax, x, y, w, h, title, kind):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0.02,rounding_size=0.18', fc='none', ec=EDGE[kind], lw=1.6, ls='--'))
    ax.text(x + 0.15, y + h - 0.15, title, ha='left', va='top', fontsize=9.2, color=EDGE[kind], fontweight='bold')


def arrow(ax, x1, y1, x2, y2, label=None, color=INK, dy=0.0, dx=0.0, size=7.6, style='-|>'):
    ax.annotate('', xy=(x2, y2), xytext=(x1, y1), arrowprops=dict(arrowstyle=style, color=color, lw=1.3, shrinkA=2, shrinkB=2))
    if label:
        ax.text((x1 + x2) / 2 + dx, (y1 + y2) / 2 + dy, label, ha='center', va='center', fontsize=size, color=color,
                bbox=dict(fc='white', ec='none', pad=0.6, alpha=0.9))


def architecture():
    fig, ax = plt.subplots(figsize=(15, 10.4))
    ax.set_xlim(0, 15)
    ax.set_ylim(-0.8, 9.8)
    ax.axis('off')
    ax.text(7.5, 9.55, 'ClaimGuard AI: architecture, trust boundaries and who may touch what', ha='center', fontsize=14,
            color=INK, fontweight='bold')
    ax.text(7.5, 9.15, 'The rule engine never calls the model. The model sees one finding at a time, cannot write a file, and cannot change a status.',
            ha='center', fontsize=9.2, color=EDGE['trusted'], fontweight='bold')

    zone(ax, 0.2, 5.1, 3.6, 3.75, 'ZONE 0  UNTRUSTED INPUT', 'untrusted')
    zone(ax, 4.2, 3.55, 6.2, 5.3, 'ZONE 1  TRUSTED CORE (deterministic, no network)', 'trusted')
    zone(ax, 10.7, 3.55, 4.1, 5.3, 'ZONE 2  MODEL SIDE', 'model')
    zone(ax, 0.2, 0.2, 14.6, 2.95, 'ZONE 3  RECORDS AND PEOPLE', 'record')

    box(ax, 0.45, 7.3, 3.1, 0.85, 'FHIR R4 bundles,\nCSV folders, JSONL claim files', 'untrusted')
    box(ax, 0.45, 6.15, 3.1, 0.85, 'Free text inside claims:\nnotes, attachment text', 'untrusted')
    box(ax, 0.45, 5.3, 3.1, 0.6, 'reaches the model only as\nlabelled, size-limited DATA', 'untrusted', size=7.8)

    box(ax, 4.45, 7.3, 2.75, 1.0, 'INGESTION\nsrc/ingest.py\nquarantines bad records', 'boundary', bold=True)
    box(ax, 7.6, 7.3, 2.6, 1.0, 'INPUT CONTRACT\nclosed claim schema\nfails closed', 'boundary', bold=True)
    box(ax, 4.45, 5.7, 2.75, 1.2, 'FACT EXTRACTOR\nsrc/facts_extractor.py\none function per rule;\nclaim data percent-encoded', 'trusted')
    box(ax, 7.6, 5.7, 2.6, 1.2, 'RULE PACK (YARA-X)\nrules/core.yar\nFAIL > UNABLE > PASS', 'trusted')
    box(ax, 4.45, 4.15, 2.75, 1.1, 'RULEBOOK DATA\nrules.json, policies.json,\ncatalogues (read-only)', 'trusted')
    box(ax, 7.6, 4.15, 2.6, 1.1, '15 RESULTS PER CLAIM\nschema-checked;\nnever a silent pass', 'trusted', bold=True)

    box(ax, 10.95, 7.15, 3.6, 1.15, 'HOSTED LANGUAGE MODEL\nMistral-Nemo (Featherless.ai)\nno tools, no files, no memory;\nreturns text only', 'model')
    box(ax, 10.95, 3.8, 3.6, 2.95, "AI GATEWAY  src/llm_adapter.py\n\nbounded prompt, note fenced\nrepair cited-path slips\nvalidate schema + citations\nkeep the review flag\ngrounding + garbled-text guard\nclosing gate (rule's action)\nany failure -> engine's own text",
        'boundary', size=8.2)

    box(ax, 0.45, 1.65, 3.3, 1.0, 'RESULTS + REVIEW EVENTS\nresults.jsonl,\nreview_decisions.jsonl', 'record')
    box(ax, 4.05, 1.65, 3.3, 1.0, 'AUDIT LOG  src/audit_log.py\nhash chain + anchor file\n(optional HMAC key)', 'record', bold=True)
    box(ax, 7.65, 1.65, 3.3, 1.0, 'REVIEW PAGE + WORKFLOW\nsrc/make_review.py,\nsrc/review_workflow.py', 'human')
    box(ax, 11.25, 1.65, 3.3, 1.0, 'HUMAN REVIEWER\nconfirm / dismiss + reason /\nrequest info / correct', 'human', bold=True)
    box(ax, 0.45, 0.4, 6.9, 0.85, 'VERIFIER  scripts/verify_audit.py (read-only):\nchain, anchor, AI ordering, result hashes', 'record', size=8)
    box(ax, 7.65, 0.4, 6.9, 0.85, 'RECHECK: a correction is a NEW run;\nthe original claim and results are never edited', 'human', size=8)

    arrow(ax, 3.55, 7.72, 4.45, 7.8, 'files in', dy=0.3)
    arrow(ax, 7.2, 7.8, 7.6, 7.8)
    arrow(ax, 8.9, 7.3, 8.9, 6.9, 'valid claim', dx=0.85)
    arrow(ax, 7.6, 6.3, 7.2, 6.3)
    arrow(ax, 5.8, 5.25, 5.8, 5.7, style='<|-')
    arrow(ax, 8.9, 5.7, 8.9, 5.25, 'outcomes', dx=0.75)
    arrow(ax, 10.2, 4.7, 10.95, 5.0, 'findings\nonly', dy=-0.5, dx=0.0)
    arrow(ax, 12.75, 6.75, 12.75, 7.15, style='<|-|>')
    arrow(ax, 7.9, 4.15, 6.3, 2.65, 'every check', dx=-0.7, dy=0.1)
    arrow(ax, 9.2, 4.15, 9.3, 2.65, 'queue', dx=0.55)
    arrow(ax, 11.6, 3.8, 6.9, 2.65, 'AI question first,\nthen answer', dx=1.6, dy=-0.05)
    arrow(ax, 10.95, 2.15, 11.25, 2.15, style='<|-|>')
    arrow(ax, 3.75, 2.15, 4.05, 2.15, style='<-')
    arrow(ax, 7.35, 2.15, 7.65, 2.15, style='<-')

    lx = 0.35
    for kind, name, step in (('untrusted', 'untrusted input', 1.6), ('boundary', 'trust boundary (validation)', 2.7),
                             ('trusted', 'trusted, deterministic', 2.3), ('model', 'model side', 1.3), ('record', 'records', 1.0),
                             ('human', 'people and review', 1.9)):
        ax.add_patch(FancyBboxPatch((lx, -0.55), 0.22, 0.16, boxstyle='round,pad=0.01', fc=COL[kind], ec=EDGE[kind], lw=1.2))
        ax.text(lx + 0.3, -0.47, name, fontsize=8, va='center', color=INK)
        lx += step + 0.6
    fig.savefig(FIG / 'architecture.png', dpi=150, bbox_inches='tight')
    plt.close(fig)


def dataflow():
    fig, ax = plt.subplots(figsize=(15, 8.6))
    ax.set_xlim(0, 15)
    ax.set_ylim(0, 8.6)
    ax.axis('off')
    ax.text(7.5, 8.3, 'Data flow of one claim, step by step (numbers match docs/22)', ha='center', fontsize=13.5, color=INK, fontweight='bold')
    steps = [
        (0.3, 6.5, '1 READ\nclaim file, FHIR bundle\nor CSV folder', 'untrusted'),
        (3.3, 6.5, '2 NORMALIZE\none claim envelope;\nbad record -> quarantine', 'boundary'),
        (6.3, 6.5, '3 FACTS\nper-rule facts and\nevidence paths', 'trusted'),
        (9.3, 6.5, '4 RULES\nYARA-X outcome for\neach of 15 rules', 'trusted'),
        (12.3, 6.5, '5 RESULTS\n15 records, schema\nchecked, never a silent pass', 'trusted'),
        (12.3, 4.5, '6 AUDIT\nrule_check x15\n(status, hash, versions)', 'record'),
        (9.3, 4.5, '7 AI QUESTION LOGGED\nBEFORE the model is called\n(only for FAIL / UNABLE)', 'record'),
        (6.3, 4.5, '8 MODEL CALL\none finding + rule excerpt,\nbounded prompt', 'model'),
        (3.3, 4.5, '9 GATEWAY\nrepair paths, validate,\nground, close, or fall back', 'boundary'),
        (0.3, 4.5, '10 AUDIT\nai_recommendation\n(which model wrote it)', 'record'),
        (0.3, 2.5, '11 ROUTING\nsystem_decision:\nroute to a human\n(never an approval)', 'record'),
        (3.3, 2.5, '12 REVIEW\nreviewer sees finding,\nevidence, explanation', 'human'),
        (6.3, 2.5, '13 DECISION\nconfirm / dismiss + reason /\nrequest info / corrected', 'human'),
        (9.3, 2.5, '14 AUDIT\ndecision recorded\n(actor, reason, time)', 'record'),
        (12.3, 2.5, '15 RECHECK\ncorrected claim = NEW run\nsteps 2 to 11 again', 'trusted'),
    ]
    for x, y, t, k in steps:
        box(ax, x, y, 2.6, 1.3, t, k, size=8.4)
    for (x1, y1, *_), (x2, y2, *_) in zip(steps, steps[1:]):
        if abs(y1 - y2) < 0.01:
            if x2 > x1:
                arrow(ax, x1 + 2.6, y1 + 0.65, x2, y2 + 0.65)
            else:
                arrow(ax, x1, y1 + 0.65, x2 + 2.6, y2 + 0.65)
        else:
            arrow(ax, x1 + 1.3, y1, x2 + 1.3, y2 + 1.3)
    ax.text(7.5, 1.85, 'Verification at any time: scripts/verify_audit.py re-checks the chain, the anchor, that every AI question precedes its answer,\n'
            'and that every result hash in the log matches a fresh run of the engine.', ha='center', fontsize=8.4, color=EDGE['record'])
    ax.text(7.5, 0.95, "Fail-closed rules along the way:  unreadable line -> quarantined, counted  |  contract failure -> 15 UNABLE results  |  rule crash -> UNABLE for that rule\n"
            "model failure, bad citation, garbled text, changed review flag -> the engine's own sentence  |  duplicate claim id -> flagged for a human",
            ha='center', fontsize=8.4, color=EDGE['untrusted'])
    fig.savefig(FIG / 'dataflow.png', dpi=150, bbox_inches='tight')
    plt.close(fig)


if __name__ == '__main__':
    FIG.mkdir(parents=True, exist_ok=True)
    architecture()
    dataflow()
    print('wrote', FIG / 'architecture.png', 'and', FIG / 'dataflow.png')
