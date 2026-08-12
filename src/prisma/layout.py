"""Adaptive PRISMA 2020 layout fixes for dynamic box heights."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from prisma_flow_diagram.prisma import (
        BoxGeometry,
        IncludedGeometries,
        LaneGeometries,
        Layout,
        MatplotlibRenderer,
        PrismaStyle,
        TextBlocks,
        Widths,
    )


def row_extent(center_y: float, left_h: float, right_h: float) -> tuple[float, float]:
    """Return (bottom, top) for a two-column row using the taller box."""
    half = max(left_h, right_h) / 2
    return center_y - half, center_y + half


def compute_start_y_center(
    ident_left_h: float,
    ident_right_h: float,
    *,
    header_y: float,
    header_h: float,
    clearance: float = 0.15,
) -> float:
    """Place the identification row below the header with a small gap."""
    max_h = max(ident_left_h, ident_right_h)
    header_bottom = header_y - header_h / 2
    return header_bottom - clearance - max_h / 2


def compute_next_row_center(
    prev_row_bottom: float,
    next_left_h: float,
    next_right_h: float,
    *,
    v_gap: float,
) -> float:
    """Position the next row so taller side boxes do not overlap the row above."""
    next_half = max(next_left_h, next_right_h) / 2
    return prev_row_bottom - v_gap - next_half


def apply_adaptive_prisma_layout() -> type:
    """Return a Prisma2020Diagram subclass with collision-aware vertical layout."""
    from prisma_flow_diagram.prisma import (
        ASSESSED,
        IDENT,
        OTHER_STEPS,
        SCREENED,
        SOUGHT,
        Box,
        LaneGeometries,
        Prisma2020Diagram,
    )

    class AdaptivePrisma2020Diagram(Prisma2020Diagram):
        def _draw_main_lane(
            self,
            *,
            renderer: MatplotlibRenderer,
            layout: Layout,
            widths: Widths,
            texts: TextBlocks,
        ) -> dict[str, BoxGeometry]:
            style = self.style
            geoms: dict[str, BoxGeometry] = {}

            ident_left_h = self.calc_box_height(texts.main_left[IDENT])
            ident_right_h = self.calc_box_height(texts.main_right[IDENT])
            y = compute_start_y_center(
                ident_left_h,
                ident_right_h,
                header_y=style.header_y,
                header_h=style.header_h,
            )

            geoms[IDENT] = renderer.draw_box(
                Box(
                    IDENT,
                    texts.main_left[IDENT],
                    layout.x_main_left,
                    y,
                    widths.w_main_left,
                    ident_left_h,
                    align="left",
                )
            )
            self._draw_side_box(
                renderer=renderer,
                ref_left=geoms[IDENT],
                text=texts.main_right[IDENT],
                x_center=layout.x_main_right,
                width=widths.w_main_right,
            )
            row_bottom, _ = row_extent(y, ident_left_h, ident_right_h)

            prev_step = IDENT
            for step in [SCREENED, SOUGHT, ASSESSED]:
                left_h = self.calc_box_height(texts.main_left[step])
                right_h = self.calc_box_height(texts.main_right[step])
                y = compute_next_row_center(
                    row_bottom,
                    left_h,
                    right_h,
                    v_gap=style.v_gap,
                )

                prev_geom = geoms[prev_step]
                next_top = y + max(left_h, right_h) / 2
                renderer.draw_arrow(
                    (prev_geom.center_x, prev_geom.bottom - style.arrow_margin),
                    (prev_geom.center_x, next_top + style.arrow_margin),
                )

                geoms[step] = renderer.draw_box(
                    Box(
                        step,
                        texts.main_left[step],
                        layout.x_main_left,
                        y,
                        widths.w_main_left,
                        left_h,
                        align="left",
                    )
                )
                self._draw_side_box(
                    renderer=renderer,
                    ref_left=geoms[step],
                    text=texts.main_right[step],
                    x_center=layout.x_main_right,
                    width=widths.w_main_right,
                )
                row_bottom, _ = row_extent(y, left_h, right_h)
                prev_step = step

            return geoms

        def _draw_lanes(
            self,
            *,
            renderer: MatplotlibRenderer,
            layout: Layout,
            widths: Widths,
            texts: TextBlocks,
        ) -> LaneGeometries:
            main_geoms = self._draw_main_lane(
                renderer=renderer,
                layout=layout,
                widths=widths,
                texts=texts,
            )

            other_geoms: dict[str, BoxGeometry] | None = None
            if texts.other_left is not None and texts.other_right is not None:
                assert layout.x_other_left is not None and layout.x_other_right is not None
                forced_y = {
                    IDENT: main_geoms[IDENT].center_y,
                    SOUGHT: main_geoms[SOUGHT].center_y,
                    ASSESSED: main_geoms[ASSESSED].center_y,
                }
                other_geoms = self._draw_vertical_flow(
                    renderer=renderer,
                    x_center=layout.x_other_left,
                    steps=OTHER_STEPS,
                    texts=texts.other_left,
                    box_width=widths.w_other_left,
                    start_y_center=main_geoms[IDENT].center_y,
                    forced_y=forced_y,
                )
                for step in [SOUGHT, ASSESSED]:
                    self._draw_side_box(
                        renderer=renderer,
                        ref_left=other_geoms[step],
                        text=texts.other_right[step],
                        x_center=layout.x_other_right,
                        width=widths.w_other_right,
                    )

            return LaneGeometries(main=main_geoms, other=other_geoms)

        def _expand_ylim(
            self,
            renderer: MatplotlibRenderer,
            lanes: LaneGeometries,
            included: IncludedGeometries,
        ) -> None:
            style = self.style
            bottoms = [geom.bottom for geom in lanes.main.values()]
            if lanes.other is not None:
                bottoms.extend(geom.bottom for geom in lanes.other.values())
            if included.included is not None:
                bottoms.append(included.included.bottom)
            if included.new is not None:
                bottoms.append(included.new.bottom)
            if included.total is not None:
                bottoms.append(included.total.bottom)

            desired_ymin = min(bottoms) - style.bottom_padding
            if desired_ymin < style.ylim[0]:
                renderer.ax.set_ylim(desired_ymin, style.ylim[1])

        def plot(
            self,
            *,
            filename: str | None = None,
            show: bool = False,
            figsize: tuple[float, float] = (14, 10),
            validation: str = "warn",
        ) -> None:
            from prisma_flow_diagram.prisma import handle_validation

            if validation != "off":
                issues = self.validate()
                handle_validation(issues, mode=validation)

            texts = self._build_text_blocks()
            has_other = texts.other_left is not None and texts.other_right is not None

            widths = self._compute_widths(texts)
            layout = self._compute_layout(widths, has_other=has_other)

            from prisma_flow_diagram.prisma import MatplotlibRenderer

            renderer = MatplotlibRenderer(
                figsize=figsize, style=self.style, xlim=layout.xlim
            )

            self._draw_headers(renderer, layout, has_other=has_other)
            lanes = self._draw_lanes(
                renderer=renderer, layout=layout, widths=widths, texts=texts
            )
            included = self._draw_included(
                renderer=renderer, layout=layout, widths=widths, texts=texts, lanes=lanes
            )
            self._draw_phase_labels(renderer=renderer, lanes=lanes, included=included)
            self._expand_ylim(renderer, lanes, included)

            if filename is not None:
                renderer.fig.savefig(filename, bbox_inches="tight", dpi=300)
            if show:
                import matplotlib.pyplot as plt

                plt.show()

    return AdaptivePrisma2020Diagram


def adaptive_prisma_style(base: PrismaStyle | None = None) -> PrismaStyle:
    """Slightly increase vertical gap when many sources inflate identification boxes."""
    from prisma_flow_diagram.prisma import PrismaStyle

    style = base or PrismaStyle()
    return replace(style, v_gap=max(style.v_gap, 0.65))
