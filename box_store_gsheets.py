"""
Google Sheets ULD / 箱型資料存取 adapter — v1.13.3.

修正重點：
1. Google Sheet 若缺少 allow_center_load，讀取時自動建立欄位。
2. 儲存 ULD 時會把完整 canonical schema 寫回 boxes worksheet。
3. 儲存後立即回讀驗證，確認 allow_center_load 等欄位真的已同步。
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st
from streamlit_gsheets import GSheetsConnection

from box_store import CANONICAL_COLUMNS, normalize_box


DEFAULT_SPREADSHEET = (
    "https://docs.google.com/spreadsheets/d/"
    "1KJntRmxBOLyl1lfEo1Sqi8MS59GNXo12z-ETlkfEX-8/"
    "edit?usp=sharing"
)
DEFAULT_WORKSHEET = "boxes"

OPTIONAL_SCHEMA_DEFAULTS = {
    "allow_center_load": False,
    "center_positions": 2,
    "enabled": True,
    "notes": "",
}


class GoogleSheetsBoxStore:
    def __init__(self):
        try:
            config = st.secrets.get("box_store", {})
        except Exception:
            config = {}

        self.spreadsheet = str(
            config.get("spreadsheet", DEFAULT_SPREADSHEET)
        ).strip() or DEFAULT_SPREADSHEET

        self.worksheet = str(
            config.get("worksheet", DEFAULT_WORKSHEET)
        ).strip() or DEFAULT_WORKSHEET

        self.conn = st.connection(
            "gsheets",
            type=GSheetsConnection,
        )

    def _read_dataframe(self) -> pd.DataFrame:
        df = self.conn.read(
            spreadsheet=self.spreadsheet,
            worksheet=self.worksheet,
            ttl=0,
        )
        return pd.DataFrame() if df is None else df.copy()

    def _ensure_optional_schema(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty and not list(df.columns):
            return df

        changed = False

        for column, default in OPTIONAL_SCHEMA_DEFAULTS.items():
            if column not in df.columns:
                df[column] = default
                changed = True

        if changed:
            self.conn.update(
                spreadsheet=self.spreadsheet,
                worksheet=self.worksheet,
                data=df,
            )

        return df

    def load_boxes(self) -> list[dict[str, Any]]:
        df = self._read_dataframe()

        if df.empty:
            return []

        df = self._ensure_optional_schema(df)
        records = []

        for raw in df.to_dict("records"):
            clean = {
                key: (None if pd.isna(value) else value)
                for key, value in raw.items()
            }
            records.append(normalize_box(clean))

        return records

    def save_boxes(self, boxes: list[dict[str, Any]]) -> None:
        records = []

        for raw in boxes:
            item = normalize_box(raw).copy()
            item["compatible_aircraft"] = ",".join(
                item.get("compatible_aircraft", [])
            )
            item["compatible_zones"] = ",".join(
                item.get("compatible_zones", [])
            )
            item["allow_center_load"] = bool(
                item.get("allow_center_load", False)
            )
            item["center_positions"] = int(
                item.get("center_positions", 2) or 2
            )
            item["enabled"] = bool(
                item.get("enabled", True)
            )
            records.append(item)

        df = pd.DataFrame(records, columns=CANONICAL_COLUMNS)

        self.conn.update(
            spreadsheet=self.spreadsheet,
            worksheet=self.worksheet,
            data=df,
        )

        verify = self._read_dataframe()

        missing_columns = [
            col for col in CANONICAL_COLUMNS
            if col not in verify.columns
        ]
        if missing_columns:
            raise RuntimeError(
                "Google Sheets 已回應更新，但缺少欄位："
                + ", ".join(missing_columns)
            )

        expected_by_id = {
            str(r["box_id"]).strip(): r
            for r in records
        }
        actual_by_id = {}

        for raw in verify.to_dict("records"):
            clean = {
                key: (None if pd.isna(value) else value)
                for key, value in raw.items()
            }
            normalized = normalize_box(clean)
            actual_by_id[str(normalized["box_id"]).strip()] = normalized

        for box_id, expected in expected_by_id.items():
            if box_id not in actual_by_id:
                raise RuntimeError(
                    f"Google Sheets 回讀驗證失敗：找不到 ULD {box_id}"
                )

            actual = actual_by_id[box_id]

            if bool(actual.get("allow_center_load", False)) != bool(
                expected.get("allow_center_load", False)
            ):
                raise RuntimeError(
                    f"Google Sheets 回讀驗證失敗："
                    f"{box_id} 的 allow_center_load 未正確同步"
                )

            if int(actual.get("center_positions", 2) or 2) != int(
                expected.get("center_positions", 2) or 2
            ):
                raise RuntimeError(
                    f"Google Sheets 回讀驗證失敗："
                    f"{box_id} 的 center_positions 未正確同步"
                )

    def connection_info(self) -> dict[str, str]:
        return {
            "backend": "Google Sheets",
            "spreadsheet": self.spreadsheet,
            "worksheet": self.worksheet,
        }

    def healthcheck(self) -> tuple[bool, str]:
        try:
            df = self._read_dataframe()
            columns = list(df.columns)
            allow_center_status = (
                "已存在"
                if "allow_center_load" in columns
                else "尚未建立（開啟 ULD 管理頁會自動建立）"
            )
            rows = len(df.index)

            return (
                True,
                "Google Sheets 連線正常"
                f"｜worksheet={self.worksheet}"
                f"｜目前 {rows} 筆 ULD"
                f"｜allow_center_load：{allow_center_status}",
            )
        except Exception as exc:
            return False, f"Google Sheets 連線失敗：{exc}"
