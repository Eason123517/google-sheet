"""
Google Sheets ULD / 箱型資料存取 adapter — v1.13.5.

- TRUE/FALSE 欄位由 normalize_box 統一解析。
- 每次 load_boxes() 先清除 Google Sheets read cache。
- save_boxes() 直接驗證 GSheetsConnection.update() 回傳 DataFrame，
  不再使用「立即回讀」判斷是否成功，避免 Sheet 已寫入卻報假錯誤。
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

    def _clear_read_cache(self) -> None:
        try:
            st.cache_data.clear()
        except Exception:
            pass

    def _read_dataframe(self, fresh: bool = False) -> pd.DataFrame:
        if fresh:
            self._clear_read_cache()

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
            updated = self.conn.update(
                spreadsheet=self.spreadsheet,
                worksheet=self.worksheet,
                data=df,
            )

            if updated is None:
                raise RuntimeError(
                    "無法建立 Google Sheets 新欄位，請確認 Service Account 編輯權限。"
                )

            self._clear_read_cache()

        return df

    def load_boxes(self) -> list[dict[str, Any]]:
        df = self._read_dataframe(fresh=True)

        if df.empty:
            return []

        df = self._ensure_optional_schema(df)
        records = []

        for raw in df.to_dict("records"):
            clean = {
                str(key).strip(): (
                    None if pd.isna(value) else value
                )
                for key, value in raw.items()
            }
            records.append(normalize_box(clean))

        return records

    def _verify_update_result(
        self,
        df: pd.DataFrame,
        expected_records: list[dict[str, Any]],
    ) -> tuple[bool, str]:
        missing_columns = [
            col
            for col in CANONICAL_COLUMNS
            if col not in df.columns
        ]

        if missing_columns:
            return False, "缺少欄位：" + ", ".join(missing_columns)

        actual_by_id = {}

        for raw in df.to_dict("records"):
            clean = {
                str(key).strip(): (
                    None if pd.isna(value) else value
                )
                for key, value in raw.items()
            }
            normalized = normalize_box(clean)
            actual_by_id[str(normalized["box_id"]).strip()] = normalized

        for expected in expected_records:
            box_id = str(expected["box_id"]).strip()

            if box_id not in actual_by_id:
                return False, f"找不到 ULD {box_id}"

            actual = actual_by_id[box_id]

            if actual["allow_center_load"] is not bool(
                expected["allow_center_load"]
            ):
                return False, f"{box_id} 的 allow_center_load 寫入資料不一致"

            if actual["enabled"] is not bool(expected["enabled"]):
                return False, f"{box_id} 的 enabled 寫入資料不一致"

            if int(actual["center_positions"]) != int(
                expected["center_positions"]
            ):
                return False, f"{box_id} 的 center_positions 寫入資料不一致"

        return True, ""

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
            item["enabled"] = bool(
                item.get("enabled", True)
            )
            item["center_positions"] = int(
                item.get("center_positions", 2) or 2
            )

            records.append(item)

        df = pd.DataFrame(
            records,
            columns=CANONICAL_COLUMNS,
        )

        # 官方 GSheetsConnection.update() 成功時會回傳本次寫入的 DataFrame。
        updated = self.conn.update(
            spreadsheet=self.spreadsheet,
            worksheet=self.worksheet,
            data=df,
        )

        if updated is None:
            raise RuntimeError(
                "Google Sheets update() 未成功，請確認 Service Account 編輯權限。"
            )

        updated_df = pd.DataFrame(updated).copy()

        ok, reason = self._verify_update_result(
            updated_df,
            records,
        )

        if not ok:
            raise RuntimeError(
                "Google Sheets 寫入資料格式驗證失敗：" + reason
            )

        self._clear_read_cache()

    def connection_info(self) -> dict[str, str]:
        return {
            "backend": "Google Sheets",
            "spreadsheet": self.spreadsheet,
            "worksheet": self.worksheet,
        }

    def healthcheck(self) -> tuple[bool, str]:
        try:
            df = self._read_dataframe(fresh=True)
            columns = [str(x).strip() for x in df.columns]

            return (
                True,
                "Google Sheets 連線正常"
                f"｜worksheet={self.worksheet}"
                f"｜目前 {len(df.index)} 筆 ULD"
                f"｜allow_center_load="
                f"{'已存在' if 'allow_center_load' in columns else '尚未建立'}"
                f"｜enabled="
                f"{'已存在' if 'enabled' in columns else '尚未建立'}",
            )
        except Exception as exc:
            return False, f"Google Sheets 連線失敗：{exc}"
