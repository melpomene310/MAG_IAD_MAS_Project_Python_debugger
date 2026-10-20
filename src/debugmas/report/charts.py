"""Графики отчёта на plotly: интерактивный .html и статичный .png той же фигуры."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

import plotly.graph_objects as go

from debugmas.eval.metrics import pareto_front

if TYPE_CHECKING:
    from debugmas.report.report import Variant

log = logging.getLogger(__name__)

# Палитра plotly в фиксированном порядке: цвет закреплён за вариантом, а не за рангом.
VARIANT_COLORS = {
    "LLM-only": "#AB63FA",
    "workflow": "#636EFA",
    "single_agent": "#00CC96",
    "mas": "#EF553B",
}
FALLBACK_COLORS = ("#FFA15A", "#19D3F3", "#FF6692", "#B6E880")
DOMINATED_COLOR = "#B0B8C4"
INK = "#2a3f5f"  # цвет текста шаблона plotly_white
MUTED = "#6b7a90"
FONT = "Inter, Open Sans, Helvetica, Arial, sans-serif"
PNG_SCALE = 2


def _color(name: str, i: int) -> str:
    base = name.split(" (")[0]
    return VARIANT_COLORS.get(base, FALLBACK_COLORS[i % len(FALLBACK_COLORS)])


def _layout(fig: go.Figure, title: str, height: int) -> None:
    fig.update_layout(
        template="plotly_white",
        title={
            "text": f"<b>{title}</b>",
            "x": 0,
            "xref": "paper",
            "xanchor": "left",
            "font": {"size": 17},
        },
        font={"family": FONT, "size": 13, "color": INK},
        height=height,
        width=860,
        margin={"l": 64, "r": 32, "t": 96, "b": 56},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "left", "x": 0},
        hoverlabel={"font": {"family": FONT}, "bgcolor": "white"},
        barcornerradius=4,
        plot_bgcolor="white",
    )
    fig.update_xaxes(showline=False, ticks="", tickfont={"color": MUTED})
    fig.update_yaxes(
        gridcolor="#eef1f5", zeroline=True, zerolinecolor="#d8dde6", tickfont={"color": MUTED}
    )


def _rate(block: dict[str, Any], key: str = "final_success") -> tuple[float, int, int]:
    m = block.get(key) or {}
    return (m.get("rate") or 0.0), m.get("k", 0), m.get("n", 0)


def success_by_bin(variants: Sequence[Variant], bins: Sequence[str]) -> go.Figure:
    """Итоговый успех по семействам задач (бинам сложности) и по всему набору (слайд 16)."""
    groups = [*bins, "Всего"]
    fig = go.Figure()
    for i, v in enumerate(variants):
        ys, custom, labels = [], [], []
        for g in groups:
            src = v.block["overall"] if g == "Всего" else v.block["by_bin"].get(g, {})
            rate, k, n = _rate(src)
            ys.append(rate)
            custom.append((k, n))
            # подписываем только итог: значения по бинам — в подсказке и таблице
            labels.append(f"{rate:.0%}" if g == "Всего" and n else "")
        fig.add_bar(
            name=v.name,
            x=groups,
            y=ys,
            marker_color=_color(v.name, i),
            text=labels,
            textposition="outside",
            textfont={"color": INK, "size": 12},
            customdata=custom,
            hovertemplate=(
                f"<b>{v.name}</b> · %{{x}}<br>решено %{{customdata[0]}} из %{{customdata[1]}}"
                " (%{y:.0%})<extra></extra>"
            ),
            cliponaxis=False,
        )
    _layout(fig, "Итоговый успех по бинам сложности", 440)
    fig.update_layout(barmode="group", bargap=0.28, bargroupgap=0.08)
    fig.update_yaxes(range=[0, 1.12], tickformat=".0%", title=None, dtick=0.25)
    return fig


def pareto(variants: Sequence[Variant]) -> go.Figure:
    """Доля успехов против цены эпизода; линия — Парето-фронт (слайд 39)."""
    points = {}
    for v in variants:
        costs = v.block["overall"]["costs"]
        points[v.name] = (costs["cost_per_episode"] or 0.0, _rate(v.block["overall"])[0])
    front = set(pareto_front(points))
    fig = go.Figure()
    line = sorted((points[n] for n in front), key=lambda p: p[0])
    if len(line) > 1:
        fig.add_scatter(
            x=[p[0] for p in line],
            y=[p[1] for p in line],
            mode="lines",
            line={"color": "#636EFA", "width": 2},
            name="Парето-фронт",
            hoverinfo="skip",
        )
    for i, v in enumerate(variants):
        cost, succ = points[v.name]
        on_front = v.name in front
        fig.add_scatter(
            x=[cost],
            y=[succ],
            mode="markers+text",
            name=v.name,
            text=[v.name],
            textposition="top center",
            textfont={"color": INK},
            marker={
                "size": 14,
                "color": _color(v.name, i) if on_front else DOMINATED_COLOR,
                "line": {"color": "white", "width": 2},
            },
            hovertemplate=(
                f"<b>{v.name}</b><br>цена эпизода $%{{x:.5f}}<br>успех %{{y:.0%}}"
                f"<br>{'на фронте' if on_front else 'есть вариант лучше'}<extra></extra>"
            ),
            showlegend=False,
            cliponaxis=False,
        )
    _layout(fig, "Качество и цена: Парето-фронт", 460)
    fig.update_xaxes(
        title="Средняя цена эпизода, $", tickformat="$.4f", rangemode="tozero", gridcolor="#eef1f5"
    )
    fig.update_yaxes(title="Доля решённых задач", tickformat=".0%", range=[0, 1.12])
    return fig


def save(fig: go.Figure, out_dir: Path, stem: str) -> dict[str, str | None]:
    """Пишет `<stem>.html` (интерактивный) и `<stem>.png` (для markdown)."""
    html = out_dir / f"{stem}.html"
    fig.write_html(html, include_plotlyjs="cdn", full_html=True)
    png: str | None = f"{stem}.png"
    try:
        fig.write_image(out_dir / png, scale=PNG_SCALE)
    except Exception as exc:  # noqa: BLE001 — без kaleido остаётся интерактивная версия
        log.warning("PNG для %s не построен (%s); остаётся только HTML", stem, exc)
        png = None
    return {"html": html.name, "png": png}


def make_charts(
    variants: Sequence[Variant], bins: Sequence[str], out_dir: Path
) -> list[dict[str, Any]]:
    charts = [
        {
            "kind": "success",
            "title": "Итоговый успех по бинам",
            **save(success_by_bin(variants, bins), out_dir, "success_by_bin"),
        }
    ]
    if len(variants) > 1:
        charts.append(
            {"kind": "pareto", "title": "Парето-фронт", **save(pareto(variants), out_dir, "pareto")}
        )
    return charts
