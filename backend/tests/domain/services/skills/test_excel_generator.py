"""Tests for excel_generator: ExcelTheme, ThemeConfig, THEMES, SemanticColors."""

from __future__ import annotations

from app.domain.services.skills.excel_generator import (
    THEMES,
    ExcelTheme,
    SemanticColors,
    ThemeConfig,
)

# ── ExcelTheme enum ────────────────────────────────────────────────────────


class TestExcelTheme:
    def test_all_twelve_members_exist(self) -> None:
        assert len(ExcelTheme) == 12

    def test_string_values(self) -> None:
        assert ExcelTheme.ELEGANT_BLACK == "elegant_black"
        assert ExcelTheme.CORPORATE_BLUE == "corporate_blue"
        assert ExcelTheme.TEAL == "teal"
        assert ExcelTheme.OLIVE == "olive"

    def test_all_members_are_strings(self) -> None:
        for theme in ExcelTheme:
            assert isinstance(theme.value, str)


# ── ThemeConfig ─────────────────────────────────────────────────────────────


class TestThemeConfig:
    def test_construction(self) -> None:
        cfg = ThemeConfig(primary="FF0000", light="FFFFFF", accent="0000FF")
        assert cfg.primary == "FF0000"
        assert cfg.light == "FFFFFF"
        assert cfg.accent == "0000FF"

    def test_header_fill_returns_primary(self) -> None:
        cfg = ThemeConfig(primary="AABBCC", light="DDEEFF", accent="112233")
        assert cfg.header_fill == "AABBCC"

    def test_alternate_row_fill_returns_light(self) -> None:
        cfg = ThemeConfig(primary="AABBCC", light="DDEEFF", accent="112233")
        assert cfg.alternate_row_fill == "DDEEFF"

    def test_chart_colors_default_empty(self) -> None:
        cfg = ThemeConfig(primary="A", light="B", accent="C")
        assert cfg.chart_colors == []

    def test_chart_colors_populated(self) -> None:
        cfg = ThemeConfig(primary="A", light="B", accent="C", chart_colors=["X", "Y"])
        assert cfg.chart_colors == ["X", "Y"]


# ── THEMES registry ────────────────────────────────────────────────────────


class TestThemesRegistry:
    def test_all_twelve_themes_present(self) -> None:
        assert len(THEMES) == 12

    def test_every_enum_member_has_config(self) -> None:
        for theme in ExcelTheme:
            assert theme in THEMES, f"Missing config for {theme.value}"

    def test_all_configs_are_theme_config_instances(self) -> None:
        for theme, config in THEMES.items():
            assert isinstance(config, ThemeConfig), f"{theme.value} config is not ThemeConfig"

    def test_all_configs_have_non_empty_primary(self) -> None:
        for theme, config in THEMES.items():
            assert config.primary, f"{theme.value} has empty primary color"

    def test_all_configs_have_non_empty_light(self) -> None:
        for theme, config in THEMES.items():
            assert config.light, f"{theme.value} has empty light color"

    def test_all_configs_have_chart_colors(self) -> None:
        for theme, config in THEMES.items():
            assert len(config.chart_colors) >= 4, f"{theme.value} has <4 chart colors"

    def test_corporate_blue_primary(self) -> None:
        assert THEMES[ExcelTheme.CORPORATE_BLUE].primary == "1F4E79"

    def test_elegant_black_primary(self) -> None:
        assert THEMES[ExcelTheme.ELEGANT_BLACK].primary == "2D2D2D"


# ── SemanticColors ──────────────────────────────────────────────────────────


class TestSemanticColors:
    def test_positive_is_green(self) -> None:
        assert SemanticColors.POSITIVE == "2E7D32"

    def test_negative_is_red(self) -> None:
        assert SemanticColors.NEGATIVE == "C62828"

    def test_warning_is_orange(self) -> None:
        assert SemanticColors.WARNING == "F57C00"

    def test_neutral_is_gray(self) -> None:
        assert SemanticColors.NEUTRAL == "757575"

    def test_all_colors_are_six_char_hex(self) -> None:
        for attr in ("POSITIVE", "NEGATIVE", "WARNING", "NEUTRAL"):
            color = getattr(SemanticColors, attr)
            assert len(color) == 6, f"{attr} is not 6 chars"
            int(color, 16)  # Should not raise
