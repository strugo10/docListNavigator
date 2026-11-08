# -*- coding: utf-8 -*-
# docListNavigator - Nawigator list i cyfr rzymskich dla MS Word i Adobe Acrobat Reader
# Autor: Sławomir Strugarek z pomocą Antigravity (Google DeepMind)
# Licencja: GNU GPL v2+

from __future__ import annotations

import os
import re
import time
import json
import threading
import urllib.request
import shutil
import tempfile
import tones
import speech
import config
import controlTypes
import textInfos
import globalPluginHandler
import ui
import wx
import gui
import api
from scriptHandler import script
from logHandler import log

# Sekcja konfiguracji dodatku w NVDA
CONFIG_SECTION = "docListNavigator"
ADDON_NAME = "docListNavigator"
ADDON_TITLE = "Nawigator list i cyfr rzymskich"
ADDON_VERSION = "1.0.7"
ADDON_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_UPDATE_SOURCE_URL = "https://raw.githubusercontent.com/strugo10/docListNavigator/main/update_info.json"

confspec = {
	"enableRomanNumerals": "boolean(default=True)",
	"romanNumeralsScope": "string(default='targetApps')",  # 'targetApps' lub 'global'
	"autoAnnounceLevel": "boolean(default=True)",
	"levelAnnouncementMode": "string(default='both')",      # 'speech', 'tone', 'both'
	"soundVolume": "integer(default=80, min=0, max=100)",
	"enableHierarchyPath": "boolean(default=True)",
	"autoCheckUpdates": "boolean(default=True)",
	"updateSourceUrl": f"string(default='{DEFAULT_UPDATE_SOURCE_URL}')",
	"lastUpdateCheckTime": "float(default=0.0)",
}
config.conf.spec[CONFIG_SECTION] = confspec


# ==============================================================================
# SŁOWNIK I TRANSFORMACJA CYFR RZYMSKICH
# ==============================================================================

ROMAN_NUMS_PL = {
	1: "jeden", 2: "dwa", 3: "trzy", 4: "cztery", 5: "pięć",
	6: "sześć", 7: "siedem", 8: "osiem", 9: "dziewięć", 10: "dziesięć",
	11: "jedenaście", 12: "dwanaście", 13: "trzynaście", 14: "czternaście", 15: "piętnaście",
	16: "szesnaście", 17: "siedemnaście", 18: "osiemnaście", 19: "dziewiętnaście", 20: "dwadzieścia",
	21: "dwadzieścia jeden", 22: "dwadzieścia dwa", 23: "dwadzieścia trzy", 24: "dwadzieścia cztery",
	25: "dwadzieścia pięć", 26: "dwadzieścia sześć", 27: "dwadzieścia siedem", 28: "dwadzieścia osiem",
	29: "dwadzieścia dziewięć", 30: "trzydzieści", 31: "trzydzieści jeden", 32: "trzydzieści dwa",
	33: "trzydzieści trzy", 34: "trzydzieści cztery", 35: "trzydzieści pięć", 36: "trzydzieści sześć",
	37: "trzydzieści siedem", 38: "trzydzieści osiem", 39: "trzydzieści dziewięć", 40: "czterdzieści",
	41: "czterdzieści jeden", 42: "czterdzieści dwa", 43: "czterdzieści trzy", 44: "czterdzieści cztery",
	45: "czterdzieści pięć", 46: "czterdzieści sześć", 47: "czterdzieści siedem", 48: "czterdzieści osiem",
	49: "czterdzieści dziewięć", 50: "pięćdziesiąt", 60: "sześćdziesiąt", 70: "siedemdziesiąt",
	80: "osiemdziesiąt", 90: "dziewięćdziesiąt", 100: "sto"
}

ROMAN_VAL_MAP = {
	'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100, 'D': 500, 'M': 1000
}


def roman_to_int(s: str) -> int:
	s = s.upper()
	total = 0
	prev_val = 0
	for char in reversed(s):
		val = ROMAN_VAL_MAP.get(char, 0)
		if val >= prev_val:
			total += val
		else:
			total -= val
		prev_val = val
	return total


def int_to_polish_words(n: int) -> str:
	if n in ROMAN_NUMS_PL:
		return ROMAN_NUMS_PL[n]
	if n < 100:
		tens = (n // 10) * 10
		units = n % 10
		t_str = ROMAN_NUMS_PL.get(tens, "")
		u_str = ROMAN_NUMS_PL.get(units, "")
		return f"{t_str} {u_str}".strip()
	return str(n)


TIRET_ORDINALS_PL = {
	1: "pierwszy", 2: "drugie", 3: "trzecie", 4: "czwarte", 5: "piąte",
	6: "szóste", 7: "siódme", 8: "ósme", 9: "dziewiąte", 10: "dziesiąte",
	11: "jedenaste", 12: "dwunaste", 13: "trzynaste", 14: "czternaste", 15: "piętnaste",
	16: "szesnaste", 17: "siedemnaste", 18: "osiemnaste", 19: "dziewiętnaste", 20: "dwudzieste"
}


# Słowa poprzedzające rzymską jedynkę 'I'
PRE_KEYWORDS = (
	r"rozdzia[łl][a-z]*|"
	r"dzia[łl][a-z]*|"
	r"art(?:yku[łl][a-z]*)?\.?|"
	r"modu[łl][a-z]*|"
	r"obszar[a-z]*|"
	r"zadani[a-z]*|"
	r"ust(?:[ęe]p)?\.?|"
	r"cz[ęe][śs][ćc][a-z]*|"
	r"pkt|punkt[a-z]*|"
	r"tabel[a-z]*|"
	r"za[łl][ąa]cznik[a-z]*|"
	r"etap[a-z]*|"
	r"faz[a-z]*|"
	r"klas[a-z]*|"
	r"wiek[a-z]*|"
	r"tom[a-z]*|"
	r"nr|numer[a-z]*"
)

# Znane cyfry rzymskie od II do L
MULTI_ROMANS = {
	"II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X",
	"XI", "XII", "XIII", "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX",
	"XXI", "XXII", "XXIII", "XXIV", "XXV", "XXVI", "XXVII", "XXVIII", "XXIX", "XXX",
	"XXXI", "XXXII", "XXXIII", "XXXIV", "XXXV", "XXXVI", "XXXVII", "XXXVIII", "XXXIX", "XL",
	"XLI", "XLII", "XLIII", "XLIV", "XLV", "XLVI", "XLVII", "XLVIII", "XLIX", "L"
}

RE_PRE_I = re.compile(rf'\b({PRE_KEYWORDS})\s+([I])\b([.,;:)]*)', re.IGNORECASE)
RE_START_I = re.compile(r'(^|[\n\r])\s*I([.)]\s*)', re.MULTILINE)
RE_MULTI_ROMAN = re.compile(r'\b([IVXLCDM]{2,}|[VXL])\b([.,;:)]*)', re.IGNORECASE)


def transform_roman_text(text: str) -> str:
	"""
	Transformuje oznaczenia cyfr rzymskich w tekście na naturalną formę mówioną 'rzymskie <liczba>',
	np. 'III' -> 'rzymskie trzy', 'w module II' -> 'w module rzymskie dwa'.
	Chroni zwykłe polskie słowo 'i' (np. 'Jan i Maria' pozostaje niezmienione).
	"""
	if not text or not isinstance(text, str):
		return text

	# 1. 'I' poprzedzone słowem kluczowym (np. 'moduł I', 'rozdział I')
	def _repl_pre_i(m):
		kw = m.group(1)
		i_token = m.group(2)
		punct = m.group(3) or ""
		# Chronimy małe 'i' będące polskim spójnikiem
		if i_token != "I":
			return m.group(0)
		return f"{kw} rzymskie jeden{punct}"
	text = RE_PRE_I.sub(_repl_pre_i, text)

	# 2. 'I' na początku linii/akapitu z kropką lub nawiasem (np. 'I. Postanowienia')
	def _repl_start_i(m):
		prefix = m.group(1) or ""
		suffix = m.group(2) or ""
		return f"{prefix}rzymskie jeden{suffix}"
	text = RE_START_I.sub(_repl_start_i, text)

	# 3. Wieloliterowe cyfry rzymskie (II, III, IV, V, VI, VII, VIII, IX, X...) oraz pojedyncze V, X, L
	def _repl_multi(m):
		raw_token = m.group(1)
		token = raw_token.upper()
		punct = m.group(2) or ""
		# Dla pojedynczych liter V, X, L wymagamy wielkiej litery w tekście źródłowym,
		# aby nie zamieniać małego 'x' (mnożenie/wymiar) ani małego 'l' (litry).
		if len(raw_token) == 1 and not raw_token.isupper():
			return m.group(0)
		if token in MULTI_ROMANS:
			val = roman_to_int(token)
			words = int_to_polish_words(val)
			return f"rzymskie {words}{punct}"
		return m.group(0)

	text = RE_MULTI_ROMAN.sub(_repl_multi, text)
	return text


# ==============================================================================
# HIERARCHICZNY KLASYFIKATOR STRUKTURY DOKUMENTU
# ==============================================================================

class LogicalLevel:
	ROZDZIAL = 0  # Rozdział IV, Dział, Tytuł, Część, Załącznik
	USTEP = 1     # ustęp 1., 1., Moduł I
	PUNKT = 2     # pkt 1), 1), Obszar A
	LITERA = 3    # litera a), a), Zadanie 1
	TIRET = 4     # tiret pierwszy, tiret drugie, –
	SUBTIRET = 5  # podwójne tiret
	BODY = 99     # Zwykła treść akapitu


LEVEL_NAMES = {
	LogicalLevel.ROZDZIAL: "Rozdział",
	LogicalLevel.USTEP: "Ustęp",
	LogicalLevel.PUNKT: "Punkt",
	LogicalLevel.LITERA: "Litera",
	LogicalLevel.TIRET: "Tiret",
	LogicalLevel.SUBTIRET: "Podwójny tiret",
	LogicalLevel.BODY: "Tekst",
}

LEVEL_SHORT_NAMES = {
	LogicalLevel.ROZDZIAL: "Rozdział",
	LogicalLevel.USTEP: "ustęp",
	LogicalLevel.PUNKT: "pkt",
	LogicalLevel.LITERA: "litera",
	LogicalLevel.TIRET: "tiret",
	LogicalLevel.SUBTIRET: "podwójne tiret",
	LogicalLevel.BODY: "tekst",
}

# Wzorce znaczników struktur prawno-dokumentowych
RE_ROZDZIAL = re.compile(
	r'^(?:(?:(?:w\s+przypadku\s+|w\s+ramach\s+)?(?:rozdzia[łl]|dzia[łl]|tytu[łl]|cz[ęe][śs][ćc]|za[łl][ąa]cznik|program))\b|[IVXLCDM]+\.\s+[A-ZĄĆĘŁŃÓŚŹŻ])',
	re.IGNORECASE
)
RE_MODUL = re.compile(
	r'^(?:(?:\d+[a-z]?\.?\s+)?(?:(?:w\s+przypadku\s+|w\s+ramach\s+|w\s+)?modu[łl][a-z]*\s+[IVXLCDM\d]+))\b',
	re.IGNORECASE
)
RE_OBSZAR = re.compile(
	r'^(?:(?:\d+[a-z]?[.)]\s+)?(?:(?:w\s+ramach\s+)?obszar(?:ze)?\s+[A-ZĄĆĘŁŃÓŚŹŻ\d]))\b',
	re.IGNORECASE
)
RE_ZADANIE = re.compile(
	r'^(?:(?:[a-z]{1,2}\)|\d+[a-z]?[.)])\s+)?(?:(?:w\s+ramach\s+|w\s+)?zadani(?:e|a|u|ach)?(?:\s+nr\.?)?(?:\s*:)?\s*[\dIVXLCDM]+(?:\s*(?:,|i|oraz|-|–)\s*[\dIVXLCDM]+)*)\b',
	re.IGNORECASE
)
RE_USTEP = re.compile(
	r'^(?:(?:art(?:yku[łl])?\.?|§|ust(?:[ęe]p)?\.?)\s*\d+[a-z]?\.?|\d+[a-z]?\.)(?:\s+|$)',
	re.IGNORECASE
)
RE_PUNKT = re.compile(
	r'^(?:(?:pkt|punkt)\s*\d+[a-z]?\.?|\d+[a-z]?\))(?:\s+|$)',
	re.IGNORECASE
)
RE_LITERA = re.compile(
	r'^(?:(?:lit(?:era)?\.?)\s*[a-z]{1,2}\.?|[a-z]{1,2}\))(?:\s+|$)',
	re.IGNORECASE
)
RE_TIRET = re.compile(r'^(?:[-–—•*]\s*)', re.IGNORECASE)
RE_SUBTIRET = re.compile(r'^(?:[-–—]{2}\s*)', re.IGNORECASE)


def _index_to_letters(idx: int) -> str:
	"""Zamienia indeks 0-bazowy na sekwencję liter: 0->a, 25->z, 26->aa, 27->ab."""
	if idx < 0:
		return "a"
	result = []
	n = idx + 1
	while n > 0:
		n, rem = divmod(n - 1, 26)
		result.append(chr(ord('a') + rem))
	return "".join(reversed(result))


def classify_paragraph(
	text: str,
	left_indent_pt: float = 0.0,
	outline_level: int = 10,
	list_level: int = -1,
	list_string: str = "",
	list_type: int = 0
) -> tuple[int, str]:
	"""
	Zwraca (logical_level, marker_text), stosując oficjalne nazewnictwo techniki prawodawczej:
	Rozdział IV -> ustęp 1. -> pkt 1) -> litera a) -> tiret pierwszy.
	"""
	if not text and not list_string:
		return LogicalLevel.BODY, ""

	raw_clean = (text or "").strip()
	cand = f"{list_string} {raw_clean}".strip() if list_string else raw_clean

	is_obszar = bool(RE_OBSZAR.match(cand))
	is_zadanie = bool(RE_ZADANIE.match(cand))
	is_modul = bool(RE_MODUL.match(cand))

	base_lvl = LogicalLevel.BODY
	base_marker = ""

	# 1. Poziom 0: Rozdział (np. Rozdział IV, IV. Struktura programu)
	if outline_level == 1 or RE_ROZDZIAL.match(cand):
		m = RE_ROZDZIAL.match(cand)
		marker = m.group(0).strip() if m else cand[:30]
		m_num = re.match(r'^(?:(?:w\s+przypadku\s+|w\s+ramach\s+)?(rozdzia[łl]|dzia[łl]|tytu[łl]|cz[ęe][śs][ćc]|za[łl][ąa]cznik|program))\s+([IVXLCDM\d]+)', cand, re.IGNORECASE)
		if m_num:
			marker = f"{m_num.group(1).capitalize()} {m_num.group(2)}"
		else:
			m_roman = re.match(r'^([IVXLCDM]+)\.', marker, re.IGNORECASE)
			if m_roman:
				marker = f"Rozdział {m_roman.group(1)}"
			elif not marker.lower().startswith("rozdzia"):
				marker = f"Rozdział: {marker}"
		return LogicalLevel.ROZDZIAL, marker

	# 2. Poziom 1: Ustęp (np. ustęp 1., 1., Moduł I) — z priorytetem dla Obszaru i Zadania (R12)
	if (is_modul or (RE_USTEP.match(cand) and not is_obszar and not is_zadanie) or (outline_level == 2 and not is_obszar and not is_zadanie and not RE_PUNKT.match(cand))):
		if is_modul:
			m_num = re.search(r'\b(?:modu[łl][a-z]*\s+([IVXLCDM\d]+))', cand, re.IGNORECASE)
			if m_num:
				v = m_num.group(1).upper()
				int_v = roman_to_int(v) if v in MULTI_ROMANS or v == 'I' else v
				base_lvl, base_marker = LogicalLevel.USTEP, f"ustęp {int_v}."
			else:
				base_lvl, base_marker = LogicalLevel.USTEP, "ustęp"
		elif RE_USTEP.match(cand):
			m_num = re.search(r'(?:(?:\b(?:art(?:yku[łl])?\.?|ust(?:[ęe]p)?\.?)|§)\s*(\d+[a-z]?)|^(\d+[a-z]?)\.)', cand, re.IGNORECASE)
			if m_num:
				num_v = m_num.group(1) or m_num.group(2)
				base_lvl, base_marker = LogicalLevel.USTEP, f"ustęp {num_v}."
			else:
				base_lvl, base_marker = LogicalLevel.USTEP, "ustęp"
		else:
			base_lvl, base_marker = LogicalLevel.USTEP, "ustęp"

	# 3. Poziom 2: Punkt (np. pkt 1), 1), Obszar A) — z priorytetem dla Zadania (R12)
	elif (is_obszar or (RE_PUNKT.match(cand) and not is_zadanie) or (outline_level == 3 and not is_zadanie and not RE_LITERA.match(cand))):
		if is_obszar:
			m_let = re.search(r'\bobszar(?:ze)?\s+([A-ZĄĆĘŁŃÓŚŹŻ\d])', cand, re.IGNORECASE)
			if m_let:
				ch_char = m_let.group(1).upper()
				if 'A' <= ch_char <= 'Z':
					num_from_letter = ord(ch_char) - ord('A') + 1
					base_lvl, base_marker = LogicalLevel.PUNKT, f"pkt {num_from_letter})"
				else:
					base_lvl, base_marker = LogicalLevel.PUNKT, f"pkt {ch_char})"
			else:
				base_lvl, base_marker = LogicalLevel.PUNKT, "pkt"
		elif RE_PUNKT.match(cand):
			m_num = re.search(r'(?:(?:pkt|punkt)\s*(\d+[a-z]?)|(\d+[a-z]?)\))', cand, re.IGNORECASE)
			if m_num:
				val = m_num.group(1) or m_num.group(2)
				base_lvl, base_marker = LogicalLevel.PUNKT, f"pkt {val})"
			else:
				base_lvl, base_marker = LogicalLevel.PUNKT, "pkt"
		else:
			base_lvl, base_marker = LogicalLevel.PUNKT, "pkt"

	# 4. Poziom 3: Litera (np. litera a), lit. c., a), Zadanie 1)
	elif is_zadanie or RE_LITERA.match(cand):
		if is_zadanie:
			m_let_pref = re.match(r'^(?:(?:lit(?:era)?\.?)\s*([a-z]{1,2})[.)]?|([a-z]{1,2})\))\s+', cand, re.IGNORECASE)
			if m_let_pref:
				let_v = (m_let_pref.group(1) or m_let_pref.group(2) or "").lower()
				base_lvl, base_marker = LogicalLevel.LITERA, f"litera {let_v})"
			else:
				base_lvl, base_marker = LogicalLevel.LITERA, "litera"
		else:
			m_let = re.match(r'^(?:(?:lit(?:era)?\.?)\s*([a-z]{1,2})[.)]?|([a-z]{1,2})\))', cand, re.IGNORECASE)
			if m_let:
				let_v = (m_let.group(1) or m_let.group(2) or "").lower()
				base_lvl, base_marker = LogicalLevel.LITERA, f"litera {let_v})"
			else:
				base_lvl, base_marker = LogicalLevel.LITERA, "litera"

	# 5. Poziom 5: Podwójny tiret
	elif RE_SUBTIRET.match(cand):
		base_lvl, base_marker = LogicalLevel.SUBTIRET, "podwójne tiret"

	# 6. Poziom 4: Tiret / Wypunktowanie
	elif RE_TIRET.match(cand):
		base_lvl, base_marker = LogicalLevel.TIRET, "tiret"

	# 7. Formatowanie natywnej listy Worda oraz uwzględnienie zagnieżdżenia (R22)
	if list_type > 0:
		if list_type == 2 or base_lvl in (LogicalLevel.TIRET, LogicalLevel.SUBTIRET):
			if list_level >= 2:
				return LogicalLevel.SUBTIRET, "podwójne tiret"
			return LogicalLevel.TIRET, "tiret"
		if base_lvl == LogicalLevel.BODY:
			if list_level <= 1:
				return LogicalLevel.USTEP, f"ustęp {list_string or '1.'}"
			elif list_level == 2:
				return LogicalLevel.PUNKT, f"pkt {list_string or '1)'}"
			elif list_level == 3:
				return LogicalLevel.LITERA, f"litera {list_string or 'a)'}"
			elif list_level == 4:
				return LogicalLevel.TIRET, "tiret"
			else:
				return LogicalLevel.SUBTIRET, "podwójne tiret"
		elif list_level >= 2 and base_lvl < list_level:
			# Zagnieżdżona lista numerowana Worda (np. '1.' na poziomie 2 pod '1.' na poziomie 1)
			raw_tok = re.sub(r'[.)\s]+$', '', (list_string or "")).strip()
			if list_level == 2:
				return LogicalLevel.PUNKT, f"pkt {raw_tok})" if raw_tok else "pkt"
			elif list_level == 3:
				return LogicalLevel.LITERA, f"litera {raw_tok.lower()})" if raw_tok else "litera"
			elif list_level == 4:
				return LogicalLevel.TIRET, "tiret"
			else:
				return LogicalLevel.SUBTIRET, "podwójne tiret"

	if base_lvl != LogicalLevel.BODY:
		return base_lvl, base_marker

	# 8. Fallback na wcięcia akapitowe
	if left_indent_pt >= 70:
		return LogicalLevel.TIRET, "tiret"
	elif left_indent_pt >= 55:
		return LogicalLevel.LITERA, "litera"
	elif left_indent_pt >= 35:
		return LogicalLevel.PUNKT, "pkt"
	elif left_indent_pt >= 15:
		return LogicalLevel.USTEP, "ustęp"

	return LogicalLevel.BODY, ""


# ==============================================================================
# STRUKTURA DANYCH ELEMENTU DOKUMENTU
# ==============================================================================

class DocumentItem:
	def __init__(self, index: int, text: str, level: int, marker: str, raw_obj=None, range_start: int = -1, range_end: int = -1, app_source: str = "word", list_level: int = -1):
		self.index = index
		self.text = text.strip()
		self.level = level
		self.marker = marker
		self.raw_obj = raw_obj
		self.range_start = range_start
		self.range_end = range_end
		self.app_source = app_source
		self.list_level = list_level
		self.parent_index = -1
		self.children_indices = []
		self.sibling_index = 1

	@property
	def display_label(self) -> str:
		snippet = self.text
		if len(snippet) > 85:
			snippet = snippet[:82] + "..."

		# 1. Tiret: np. "tiret pierwszy: pomoc w zakupie...", "tiret drugie: pomoc..."
		if self.level == LogicalLevel.TIRET:
			clean_snip = re.sub(r'^[-–—•*]\s*', '', snippet)
			t_marker = self.marker if self.marker and self.marker.startswith("tiret") else "tiret"
			return f"{t_marker}: {clean_snip}"

		# 2. Podwójny tiret
		if self.level == LogicalLevel.SUBTIRET:
			clean_snip = re.sub(r'^[-–—]{2}\s*', '', snippet)
			return f"podwójne tiret: {clean_snip}"

		# 3. Rozdział: np. "Rozdział IV. Struktura programu"
		if self.level == LogicalLevel.ROZDZIAL:
			m_rom = re.match(r'^([IVXLCDM]+)\.\s*(.*)', snippet, re.IGNORECASE)
			if m_rom:
				return f"Rozdział {m_rom.group(1)}. {m_rom.group(2)}"
			if snippet.lower().startswith("rozdzia"):
				return snippet
			return f"Rozdział: {snippet}"

		# 4. Ustęp, Punkt, Litera
		clean_snip = snippet
		m_prefix = re.match(r'^(?:\d+[a-z]?[.)]|[a-z]{1,2}\))\s*(.*)', clean_snip)
		if m_prefix:
			clean_snip = m_prefix.group(1)

		if self.marker:
			if clean_snip.lower().startswith(self.marker.lower()):
				return clean_snip
			return f"{self.marker} {clean_snip}"

		prefix = LEVEL_SHORT_NAMES.get(self.level, "")
		return f"{prefix} {clean_snip}"

	@property
	def tree_label(self) -> str:
		indent = "  " * min(self.level, 8)
		disp = self.display_label
		if len(disp) > 75:
			disp = disp[:72] + "..."
		return f"{indent}{disp}"


# ==============================================================================
# OKNO DRZEWA STRUKTURY DOKUMENTU (WCAG 2.2 AA)
# ==============================================================================

class DocumentStructureDialog(wx.Dialog):
	"""
	Dostępne, czytelne okno drzewa struktury dokumentu z natychmiastowym filtrowaniem
	i skrótem F1 wyświetlającym pomoc.
	"""
	def __init__(self, parent, title, items: list[DocumentItem], current_index: int, on_select_callback):
		super().__init__(parent, title=title, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		self.items = items
		self.current_index = current_index
		self.on_select_callback = on_select_callback
		self.filtered_items = list(items)

		self.SetSize((720, 560))
		self.CentreOnScreen()

		panel = wx.Panel(self)
		mainSizer = wx.BoxSizer(wx.VERTICAL)

		# 1. Pole wyszukiwania z czytelną etykietą
		lblSearch = wx.StaticText(panel, label="&Filtruj strukturę dokumentu (wpisz słowo lub numer):")
		mainSizer.Add(lblSearch, 0, wx.ALL, 8)

		self.txtSearch = wx.TextCtrl(panel, style=wx.TE_PROCESS_ENTER)
		self.txtSearch.SetHint("Wpisz np. 'Zadanie 1', 'Obszar B', 'art. 3'...")
		self.txtSearch.Bind(wx.EVT_TEXT, self.onSearchText)
		self.txtSearch.Bind(wx.EVT_TEXT_ENTER, self.onEnterPressed)
		mainSizer.Add(self.txtSearch, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 8)

		# 2. Lista elementów struktury (ListBox z pełną obsługą klawiatury)
		lblList = wx.StaticText(panel, label="&Elementy hierarchiczne dokumentu:")
		mainSizer.Add(lblList, 0, wx.ALL, 8)

		self.listCtrl = wx.ListBox(panel, style=wx.LB_SINGLE | wx.LB_HSCROLL)
		self.listCtrl.Bind(wx.EVT_KEY_DOWN, self.onListKeyDown)
		mainSizer.Add(self.listCtrl, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)

		# 3. Pasek przycisków
		btnSizer = wx.BoxSizer(wx.HORIZONTAL)
		self.btnHelp = wx.Button(panel, label="Pomoc (&F1)")
		self.btnHelp.Bind(wx.EVT_BUTTON, self.onHelp)
		btnSizer.Add(self.btnHelp, 0, wx.RIGHT, 8)

		btnSizer.AddStretchSpacer()

		self.btnOk = wx.Button(panel, wx.ID_OK, label="&Przejdź do elementu (Enter)")
		self.btnOk.Bind(wx.EVT_BUTTON, self.onOk)
		btnSizer.Add(self.btnOk, 0, wx.RIGHT, 8)

		self.btnCancel = wx.Button(panel, wx.ID_CANCEL, label="&Anuluj (Esc)")
		btnSizer.Add(self.btnCancel, 0)

		mainSizer.Add(btnSizer, 0, wx.EXPAND | wx.ALL, 8)
		panel.SetSizer(mainSizer)

		self.populateList()
		self.txtSearch.SetFocus()

		self.Bind(wx.EVT_CHAR_HOOK, self.onCharHook)

	def populateList(self, filter_query: str = ""):
		self.listCtrl.Clear()
		q = filter_query.strip().lower()
		self.filtered_items = []

		for it in self.items:
			if not q or q in it.text.lower() or q in it.marker.lower() or q in LEVEL_NAMES.get(it.level, "").lower():
				self.filtered_items.append(it)
				self.listCtrl.Append(it.tree_label)

		# Zaznacz pozycję najbliższą obecnej
		if self.filtered_items:
			target_pos = 0
			for idx, fit in enumerate(self.filtered_items):
				if fit.index == self.current_index:
					target_pos = idx
					break
			self.listCtrl.SetSelection(target_pos)

	def onSearchText(self, event):
		self.populateList(self.txtSearch.GetValue())

	def onEnterPressed(self, event):
		self.onOk(event)

	def onListKeyDown(self, event):
		key = event.GetKeyCode()
		if key in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
			self.onOk(event)
		elif key == wx.WXK_F1:
			self.onHelp(event)
		else:
			event.Skip()

	def onCharHook(self, event):
		key = event.GetKeyCode()
		if key == wx.WXK_ESCAPE:
			self.EndModal(wx.ID_CANCEL)
		elif key == wx.WXK_F1:
			self.onHelp(None)
		else:
			event.Skip()

	def onHelp(self, event):
		help_text = (
			"NAWIGATOR LIST I CYFR RZYMSKICH — DRZEWO STRUKTURY\n"
			+ "=" * 60 + "\n\n"
			"KLAWISZE NAWIGACYJNE W TYM OKNIE:\n"
			"- Strzałka w dół / w górę: poruszanie się po elementach dokumentu\n"
			"- Enter: przejście bezpośrednio do wybranego punktu w Word/Acrobat\n"
			"- Wpisanie tekstu w polu wyszukiwania: natychmiastowe filtrowanie listy\n"
			"- Escape: zamknięcie okna bez zmiany pozycji\n"
			"- F1: ponowne wyświetlenie tej pomocy\n"
		)
		ui.browseableMessage(help_text, "Pomoc: Drzewo struktury dokumentu")

	def onOk(self, event):
		sel = self.listCtrl.GetSelection()
		if sel != wx.NOT_FOUND and sel < len(self.filtered_items):
			target_item = self.filtered_items[sel]
			if self.on_select_callback:
				self.on_select_callback(target_item)
		self.EndModal(wx.ID_OK)


# ==============================================================================
# MODUŁ AKTUALIZACJI DODATKU (WCAG 2.1 / 2.2 AA)
# ==============================================================================

def _parse_version(v_str: str) -> tuple:
	parts = re.findall(r'\d+', str(v_str or ""))
	return tuple(int(p) for p in parts) if parts else (0,)

def _is_newer(remote_v: str, local_v: str) -> bool:
	return _parse_version(remote_v) > _parse_version(local_v)


class UpdateNotificationDialog(wx.Dialog):
	"""
	W pełni dostępne okno powiadomienia o aktualizacji (WCAG 2.1 / 2.2 AA).
	"""
	def __init__(self, parent, addon_title, local_ver, remote_ver, changelog, on_install_callback):
		super().__init__(parent, title=f"Aktualizacja dodatku: {addon_title}", style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		self.on_install_callback = on_install_callback
		self.SetSize((620, 460))
		self.CentreOnScreen()

		panel = wx.Panel(self)
		mainSizer = wx.BoxSizer(wx.VERTICAL)

		header = wx.StaticText(panel, label=f"Dostępna jest nowa wersja dodatku: {addon_title}")
		font = header.GetFont()
		font.SetWeight(wx.FONTWEIGHT_BOLD)
		font.SetPointSize(font.GetPointSize() + 2)
		header.SetFont(font)
		mainSizer.Add(header, 0, wx.ALL, 10)

		infoTxt = f"Zainstalowana wersja: {local_ver}\nNowa dostępna wersja: {remote_ver}"
		lblInfo = wx.StaticText(panel, label=infoTxt)
		mainSizer.Add(lblInfo, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

		lblChangelog = wx.StaticText(panel, label="&Wykaz wprowadzonych zmian i usprawnień:")
		mainSizer.Add(lblChangelog, 0, wx.LEFT | wx.RIGHT, 10)

		self.txtChangelog = wx.TextCtrl(panel, value=changelog or "Brak opisu zmian.", style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_WORDWRAP)
		mainSizer.Add(self.txtChangelog, 1, wx.EXPAND | wx.ALL, 10)

		btnSizer = wx.BoxSizer(wx.HORIZONTAL)
		self.btnInstall = wx.Button(panel, wx.ID_OK, label="&Zainstaluj aktualizację teraz")
		self.btnInstall.Bind(wx.EVT_BUTTON, self.onInstall)
		btnSizer.Add(self.btnInstall, 0, wx.RIGHT, 10)

		self.btnLater = wx.Button(panel, wx.ID_CANCEL, label="Przypomnij &później")
		btnSizer.Add(self.btnLater, 0)

		mainSizer.Add(btnSizer, 0, wx.ALIGN_RIGHT | wx.ALL, 10)
		panel.SetSizer(mainSizer)

		self.btnInstall.SetFocus()
		self.Bind(wx.EVT_CHAR_HOOK, self.onCharHook)

	def onCharHook(self, event):
		if event.GetKeyCode() == wx.WXK_ESCAPE:
			self.EndModal(wx.ID_CANCEL)
		else:
			event.Skip()

	def onInstall(self, event):
		if self.on_install_callback:
			self.on_install_callback()
		self.EndModal(wx.ID_OK)


class AddonUpdaterEngine:
	def __init__(self, addon_name: str, addon_title: str, current_version: str, addon_dir: str, config_section: str):
		self.addon_name = addon_name
		self.addon_title = addon_title
		self.current_version = current_version
		self.addon_dir = addon_dir
		self.config_section = config_section
		self.override_source_url = ""

	def get_candidate_sources(self) -> list[str]:
		sources = []
		override_url = (getattr(self, "override_source_url", "") or "").strip()
		if override_url:
			sources.append(override_url)
		conf = config.conf.get(self.config_section, {})
		custom_url = (conf.get("updateSourceUrl", "") or "").strip()
		if custom_url:
			sources.append(custom_url)

		sources.append(DEFAULT_UPDATE_SOURCE_URL)
		if self.addon_dir:
			sources.append(os.path.join(self.addon_dir, "update_info.json"))

		sources.extend([
			r"G:\Mój dysk\Antigravity\Nvda dodatki\updates.json",
			r"C:\Antigravity\Nvda dodatki\updates.json",
		])
		deduped = []
		for s in sources:
			if s and s not in deduped:
				deduped.append(s)
		return deduped

	def fetch_manifest(self) -> tuple[dict | None, str | None]:
		sources = self.get_candidate_sources()
		raw_content = None
		resolved_source = None
		last_err = None

		for s in sources:
			try:
				if s.startswith("http://") or s.startswith("https://"):
					req = urllib.request.Request(s, headers={"User-Agent": "NVDA-Addon-Updater/1.0"})
					with urllib.request.urlopen(req, timeout=10) as resp:
						raw_content = resp.read().decode("utf-8-sig")
						resolved_source = s
						break
				elif os.path.isfile(s):
					with open(s, "r", encoding="utf-8-sig") as f:
						raw_content = f.read()
						resolved_source = s
						break
			except Exception as ex:
				last_err = ex
				continue

		if not raw_content:
			return None, str(last_err or "Nie znaleziono pliku ogłoszeniowego na dysku ani pod wskazanym adresem.")

		try:
			data = json.loads(raw_content)
			if self.addon_name in data and isinstance(data[self.addon_name], dict):
				item = data[self.addon_name]
			elif isinstance(data, dict) and "version" in data:
				item = data
			else:
				return None, f"Brak wpisu dla dodatku '{self.addon_name}' w pliku ogłoszeniowym."

			item["_source"] = resolved_source
			return item, None
		except Exception as ex:
			return None, f"Błąd przetwarzania formatu JSON: {ex}"

	def check_for_updates(self, manual: bool = False):
		t = threading.Thread(target=self._worker_check, args=(manual,), daemon=True)
		t.start()

	def _worker_check(self, manual: bool):
		try:
			info, err = self.fetch_manifest()
			if not info:
				if manual:
					msg = f"Nie udało się sprawdzić aktualizacji dla dodatku {self.addon_title}.\n\nSzczegóły: {err}"
					wx.CallAfter(gui.messageBox, msg, f"Aktualizacje: {self.addon_title}", wx.OK | wx.ICON_WARNING)
				return

			remote_ver = str(info.get("version", "")).strip()
			if _is_newer(remote_ver, self.current_version):
				try:
					config.conf[self.config_section]["lastUpdateCheckTime"] = time.time()
				except Exception:
					pass
				download_url = info.get("downloadUrl", "")
				changelog = info.get("changelog", "")

				def _show_dialog():
					def _on_confirm():
						self.perform_update(download_url)
					dlg = UpdateNotificationDialog(
						parent=gui.mainFrame,
						addon_title=self.addon_title,
						local_ver=self.current_version,
						remote_ver=remote_ver,
						changelog=changelog,
						on_install_callback=_on_confirm
					)
					gui.mainFrame.prePopup()
					dlg.ShowModal()
					dlg.Destroy()
					gui.mainFrame.postPopup()

				wx.CallAfter(_show_dialog)
			else:
				if manual:
					msg = f"Posiadasz najnowszą wersję dodatku {self.addon_title} ({self.current_version}).\nBrak nowszych aktualizacji."
					wx.CallAfter(gui.messageBox, msg, f"Aktualizacje: {self.addon_title}", wx.OK | wx.ICON_INFORMATION)
		except Exception as ex:
			if manual:
				wx.CallAfter(gui.messageBox, f"Wystąpił nieoczekiwany błąd podczas sprawdzania aktualizacji:\n{ex}", f"Błąd: {self.addon_title}", wx.OK | wx.ICON_ERROR)

	def perform_update(self, download_url: str):
		t = threading.Thread(target=self._worker_download_install, args=(download_url,), daemon=True)
		t.start()

	def _worker_download_install(self, download_url: str):
		target_pkg = None
		try:
			import addonHandler
			wx.CallAfter(ui.message, f"Pobieranie aktualizacji dla {self.addon_title}...")

			dl_clean = (download_url or "").strip()
			if not dl_clean:
				raise ValueError("Brak adresu pakietu instalacyjnego w pliku ogłoszeniowym.")

			if dl_clean.startswith("http://") or dl_clean.startswith("https://"):
				req = urllib.request.Request(dl_clean, headers={"User-Agent": "NVDA-Addon-Updater/1.0"})
				tmp_file = os.path.join(tempfile.gettempdir(), f"{self.addon_name}_update_{os.getpid()}.nvda-addon")
				with urllib.request.urlopen(req, timeout=30) as resp, open(tmp_file, "wb") as out:
					shutil.copyfileobj(resp, out)
				target_pkg = tmp_file
			else:
				if not dl_clean.lower().endswith(".nvda-addon"):
					raise ValueError(f"Odrzucono plik spoza formatu pakietu dodatku NVDA (.nvda-addon): {dl_clean}")
				candidates = [dl_clean]
				candidates.extend([
					os.path.join(r"G:\Mój dysk\Antigravity\Nvda dodatki\Pakiety_Instalacyjne", f"{self.addon_name}.nvda-addon"),
					os.path.join(r"C:\Antigravity\Nvda dodatki\Pakiety_Instalacyjne", f"{self.addon_name}.nvda-addon"),
				])
				for cand in candidates:
					if cand and cand.lower().endswith(".nvda-addon") and os.path.isfile(cand):
						target_pkg = cand
						break

			if not target_pkg or not target_pkg.lower().endswith(".nvda-addon") or not os.path.isfile(target_pkg):
				raise FileNotFoundError(f"Nie znaleziono prawidłowego pliku instalacyjnego dodatku (.nvda-addon):\n{download_url}")

			if not hasattr(addonHandler, "AddonBundle") or not hasattr(addonHandler, "installAddonBundle"):
				raise RuntimeError("Bieżąca instancja NVDA nie udostępnia API instalacji pakietów addonHandler.")

			bundle = addonHandler.AddonBundle(target_pkg)
			bundle_name = (bundle.manifest.get("name") or "").strip()
			if bundle_name != self.addon_name:
				raise ValueError(f"Niezgodna nazwa dodatku w pakiecie: oczekiwano '{self.addon_name}', otrzymano '{bundle_name}'.")

			def _do_install():
				try:
					try:
						from addonHandler import addonVersionCheck
						if hasattr(addonVersionCheck, "isAddonCompatible") and not addonVersionCheck.isAddonCompatible(bundle):
							gui.messageBox(
								f"Pakiet aktualizacji dodatku {self.addon_title} nie jest zgodny z bieżącą wersją NVDA.",
								f"Niezgodna wersja: {self.addon_title}",
								wx.OK | wx.ICON_ERROR
							)
							return
					except Exception:
						pass

					prev_addon = None
					if hasattr(addonHandler, "getAvailableAddons"):
						for a in addonHandler.getAvailableAddons():
							if getattr(a, "name", None) == self.addon_name:
								prev_addon = a
								break

					addon_obj = addonHandler.installAddonBundle(bundle)
					install_errors = getattr(bundle, "_installExceptions", None)
					if addon_obj is None or install_errors:
						raise RuntimeError(f"Instalacja pakietu nie powiodła się: {install_errors or 'brak obiektu dodatku'}")

					if prev_addon is not None and not getattr(prev_addon, "isPendingRemove", False):
						prev_addon.requestRemove()

					try:
						import core
						res = gui.messageBox(
							f"Aktualizacja dodatku {self.addon_title} została pomyślnie zainstalowana.\nCzy chcesz teraz ponownie uruchomić NVDA, aby zastosować zmiany?",
							f"Zainstalowano aktualizację: {self.addon_title}",
							wx.YES_NO | wx.ICON_QUESTION
						)
						if res == wx.YES:
							core.restart()
					except Exception:
						pass
				except Exception as ex2:
					log.error(f"{self.addon_name} updater internal install error: {ex2}")
					gui.messageBox(f"Nie udało się zainstalować aktualizacji dodatku:\n{ex2}", "Błąd instalacji", wx.OK | wx.ICON_ERROR)

			wx.CallAfter(_do_install)
		except Exception as ex:
			wx.CallAfter(gui.messageBox, f"Nie udało się pobrać lub zweryfikować aktualizacji:\n{ex}", f"Błąd aktualizacji: {self.addon_title}", wx.OK | wx.ICON_ERROR)


# ==============================================================================
# PANEL USTAWIEŃ W PREFERENCJACH NVDA
# ==============================================================================

try:
	from gui.settingsDialogs import SettingsPanel
except Exception:
	SettingsPanel = getattr(gui, "SettingsPanel", object)


class DocListNavigatorSettingsPanel(SettingsPanel):
	title = "Nawigator list i cyfr rzymskich"

	def makeSettings(self, settingsSizer):
		try:
			self._makeSettingsInternal(settingsSizer)
		except Exception as e:
			log.error(f"docListNavigator: Błąd podczas budowania panelu ustawień: {e}", exc_info=True)
			errLabel = wx.StaticText(self, label=f"Wystąpił błąd podczas ładowania panelu ustawień: {e}")
			settingsSizer.Add(errLabel, flag=wx.ALL, border=15)

	def _makeSettingsInternal(self, settingsSizer):
		sHelper = gui.guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
		conf = config.conf[CONFIG_SECTION]

		# 1. Cyfry rzymskie
		self.chkRoman = sHelper.addItem(
			wx.CheckBox(self, label="&Naturalna wymowa cyfr rzymskich (np. 'rzymskie trzy' zamiast 'III')")
		)
		self.chkRoman.SetValue(conf.get("enableRomanNumerals", True))

		# Zakres wymowy
		scopes = [
			("targetApps", "Tylko w Microsoft Word i Adobe Acrobat Reader (zalecane)"),
			("global", "Globalnie we wszystkich aplikacjach"),
		]
		self.scopeChoices = [label for _, label in scopes]
		self.scopeKeys = [key for key, _ in scopes]
		curScope = conf.get("romanNumeralsScope", "targetApps")
		curIdx = self.scopeKeys.index(curScope) if curScope in self.scopeKeys else 0

		self.choiceScope = sHelper.addLabeledControl(
			"&Zakres działania wymowy cyfr rzymskich:",
			wx.Choice,
			choices=self.scopeChoices
		)
		self.choiceScope.SetSelection(curIdx)

		# 2. Nawigacja po listach
		settingsSizer.AddSpacer(10)
		self.chkAutoLevel = sHelper.addItem(
			wx.CheckBox(self, label="&Automatycznie sygnalizuj zmianę poziomu listy podczas czytania strzałkami")
		)
		self.chkAutoLevel.SetValue(conf.get("autoAnnounceLevel", True))

		modes = [
			("both", "Mowa oraz dyskretny dźwięk (zalecane)"),
			("speech", "Tylko komunikat mowy (np. 'Poziom 2')"),
			("tone", "Tylko dyskretny dźwięk"),
		]
		self.modeChoices = [label for _, label in modes]
		self.modeKeys = [key for key, _ in modes]
		curMode = conf.get("levelAnnouncementMode", "both")
		curModeIdx = self.modeKeys.index(curMode) if curMode in self.modeKeys else 0

		self.choiceMode = sHelper.addLabeledControl(
			"&Sposób sygnalizowania zmiany poziomu:",
			wx.Choice,
			choices=self.modeChoices
		)
		self.choiceMode.SetSelection(curModeIdx)

		# 3. Głośność dźwięków
		self.sliderVol = sHelper.addLabeledControl(
			"&Głośność dźwięków nawigatora (%):",
			wx.Slider,
			minValue=0,
			maxValue=100,
			value=conf.get("soundVolume", 80),
			style=wx.SL_HORIZONTAL | wx.SL_LABELS
		)

		# 4. Aktualizacje dodatku (WCAG 2.1 / 2.2 AA)
		settingsSizer.AddSpacer(10)
		self.chkAutoUpdates = sHelper.addItem(
			wx.CheckBox(self, label="&Automatycznie sprawdzaj dostępność aktualizacji przy uruchomieniu NVDA")
		)
		self.chkAutoUpdates.SetValue(conf.get("autoCheckUpdates", True))

		self.txtUpdateSource = sHelper.addLabeledControl(
			"&Lokalizacja pliku ogłoszeniowego (ścieżka na dysku lub URL):",
			wx.TextCtrl,
			value=conf.get("updateSourceUrl", DEFAULT_UPDATE_SOURCE_URL)
		)

		# 5. Przyciski akcji
		settingsSizer.AddSpacer(10)
		btnBox = wx.BoxSizer(wx.HORIZONTAL)
		self.btnCheckUpdates = wx.Button(self, label="&Sprawdź dostępność aktualizacji teraz")
		self.btnCheckUpdates.Bind(wx.EVT_BUTTON, self.onCheckUpdatesNow)
		btnBox.Add(self.btnCheckUpdates, 0, wx.RIGHT, 8)

		self.btnTestSpeech = wx.Button(self, label="Przetestuj wymowę: 'moduł III, rozdział VI, ustęp 3a'")
		self.btnTestSpeech.Bind(wx.EVT_BUTTON, self.onTestSpeech)
		btnBox.Add(self.btnTestSpeech, 0, wx.RIGHT, 8)

		self.btnHelp = wx.Button(self, label="Pomoc ze skrótami (F1)")
		self.btnHelp.Bind(wx.EVT_BUTTON, self.onHelp)
		btnBox.Add(self.btnHelp, 0)

		sHelper.addItem(btnBox)

	def onCheckUpdatesNow(self, event):
		updater = AddonUpdaterEngine(
			addon_name=ADDON_NAME,
			addon_title=ADDON_TITLE,
			current_version=ADDON_VERSION,
			addon_dir=ADDON_DIR,
			config_section=CONFIG_SECTION
		)
		try:
			if hasattr(self, "txtUpdateSource") and self.txtUpdateSource is not None:
				current_url = (self.txtUpdateSource.GetValue() or "").strip()
				if current_url:
					updater.override_source_url = current_url
		except Exception:
			pass
		updater.check_for_updates(manual=True)

	def onTestSpeech(self, event):
		sample = "W przypadku modułu III Zadanie 1. Rozdział VI, ustęp 3a litera b tiret drugi."
		transformed = transform_roman_text(sample)
		speech.speakText(transformed)

	def onHelp(self, event):
		help_text = (
			"DODATEK: NAWIGATOR LIST I CYFR RZYMSKICH DLA WORD I ACROBAT\n"
			+ "=" * 65 + "\n\n"
			"GŁÓWNE SKRÓTY KLAWISZOWE W MICROSOFT WORD ORAZ ADOBE ACROBAT:\n"
			"- NVDA + Alt + L: Odczytanie pełnej ścieżki hierarchicznej (np. 'Rozdział VI > ustęp 1 > punkt 1 > litera a')\n"
			"  (Dwukrotne szybkie wciśnięcie kopiuje pełną ścieżkę do schowka)\n"
			"- NVDA + Alt + Strzałka w dół: Przejście do NASTĘPNEGO punktu na tym samym poziomie\n"
			"- NVDA + Alt + Strzałka w górę: Przejście do POPRZEDNIEGO punktu na tym samym poziomie\n"
			"- NVDA + Alt + Strzałka w lewo: Skok do ELEMENTU NADRZĘDNEGO (poziom wyżej, np. z litery 'a)' do punktu '1)')\n"
			"- NVDA + Alt + Strzałka w prawo: Skok do PIERWSZEGO PODPUNKTU (poziom niżej, np. z punktu '1)' do litery 'a)')\n"
			"- NVDA + Alt + F7: Otwarcie okna drzewa struktury dokumentu z szybkim wyszukiwaniem\n"
			"- NVDA + Ctrl + Shift + L: Szybkie włączenie/wyłączenie automatycznego ogłaszania zmiany poziomów\n"
			"- NVDA + Ctrl + Shift + R: Szybkie przełączenie wymowy cyfr rzymskich\n\n"
			"Wszystkie skróty można dostosować w: Menu NVDA -> Preferencje -> Zdarzenia wejścia.\n"
		)
		ui.browseableMessage(help_text, "Pomoc: Nawigator list i cyfr rzymskich")

	def onSave(self):
		conf = config.conf[CONFIG_SECTION]
		conf["enableRomanNumerals"] = self.chkRoman.GetValue()
		selScope = self.choiceScope.GetSelection()
		if selScope != wx.NOT_FOUND:
			conf["romanNumeralsScope"] = self.scopeKeys[selScope]
		conf["autoAnnounceLevel"] = self.chkAutoLevel.GetValue()
		selMode = self.choiceMode.GetSelection()
		if selMode != wx.NOT_FOUND:
			conf["levelAnnouncementMode"] = self.modeKeys[selMode]
		conf["soundVolume"] = self.sliderVol.GetValue()
		conf["autoCheckUpdates"] = self.chkAutoUpdates.GetValue()
		conf["updateSourceUrl"] = self.txtUpdateSource.GetValue().strip()


# ==============================================================================
# GŁÓWNA KLASA WTYCZKI GLOBALNEJ
# ==============================================================================

_orig_speak = None
_orig_manager_speak = None
_orig_speak_spelling = None
_orig_cursor_set_selection = None


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	scriptCategory = "Nawigator list i cyfr rzymskich"

	__gestures = {
		"kb:NVDA+alt+downArrow": "nextSameLevel",
		"kb:NVDA+alt+upArrow": "prevSameLevel",
		"kb:NVDA+alt+leftArrow": "jumpParent",
		"kb:NVDA+alt+rightArrow": "jumpFirstChild",
		"kb:NVDA+alt+l": "speakBreadcrumb",
		"kb:NVDA+alt+f7": "showStructureTree",
		"kb:NVDA+control+shift+l": "toggleAutoLevel",
		"kb:NVDA+control+shift+r": "toggleRomanNumerals",
		"kb:NVDA+control+shift+h": "showHelp",
	}

	def getScript(self, gesture):
		script = super().getScript(gesture)
		if not script:
			return None
		# Skróty nawigacji po dokumentach (strzałki z Alt, F7, breadcrumb)
		# powinny działać wyłącznie wtedy, gdy aktywny jest Word lub Acrobat.
		# Poza nimi zwracamy None, aby NVDA przekazało gest dalej (np. do przeglądarki).
		script_name = getattr(script, "__name__", "")
		doc_scripts = {
			"script_nextSameLevel",
			"script_prevSameLevel",
			"script_jumpParent",
			"script_jumpFirstChild",
			"script_speakBreadcrumb",
			"script_showStructureTree",
		}
		if script_name in doc_scripts and not self._is_target_application_active():
			return None
		return script

	def __init__(self):
		super().__init__()
		self._last_announced_level = -1
		self._last_speech_time = 0
		self._last_breadcrumb_press = 0
		self._in_spelling_mode = 0
		self._filter_registered = False
		self._startup_update_timer = None

		# Szybka pamięć podręczna (cache) struktury dokumentu Worda
		self._word_cache_items = []
		self._word_cache_doc = ""
		self._word_cache_key = None
		self._word_cache_time = 0.0

		# Rejestracja panelu ustawień
		gui.settingsDialogs.NVDASettingsDialog.categoryClasses.append(DocListNavigatorSettingsPanel)

		# Przechwytywanie potoku mowy dla cyfr rzymskich (w tym SayAll i ochrona literowania — R01, R02)
		global _orig_speak, _orig_manager_speak, _orig_speak_spelling, _orig_cursor_set_selection
		try:
			if hasattr(speech, "extensions") and hasattr(speech.extensions, "filter_speechSequence"):
				speech.extensions.filter_speechSequence.register(self._filter_speech_sequence)
				self._filter_registered = True
		except Exception as ex:
			log.debug(f"docListNavigator: rejestracja filter_speechSequence nie powiodła się: {ex}")

		if _orig_speak is None:
			if hasattr(speech, "speech") and hasattr(speech.speech, "speak"):
				_orig_speak = speech.speech.speak
				speech.speech.speak = self._custom_speak
			if hasattr(speech, "speak"):
				if _orig_speak is None:
					_orig_speak = speech.speak
				speech.speak = self._custom_speak

		try:
			if _orig_manager_speak is None and hasattr(speech, "speech") and hasattr(speech.speech, "_manager"):
				mgr = getattr(speech.speech, "_manager", None)
				if mgr is not None and hasattr(mgr, "speak"):
					_orig_manager_speak = mgr.speak
					mgr.speak = self._custom_manager_speak
		except Exception:
			pass

		try:
			if hasattr(speech, "sayAll") and getattr(speech.sayAll, "SayAllHandler", None) is not None:
				sah = speech.sayAll.SayAllHandler
				swp = getattr(sah, "_speechWithoutPausesInstance", None)
				if swp is not None and hasattr(swp, "speak"):
					swp.speak = self._custom_speak
		except Exception:
			pass

		if _orig_speak_spelling is None:
			if hasattr(speech, "speech") and hasattr(speech.speech, "speakSpelling"):
				_orig_speak_spelling = speech.speech.speakSpelling
				speech.speech.speakSpelling = self._custom_speak_spelling
			if hasattr(speech, "speakSpelling"):
				if _orig_speak_spelling is None:
					_orig_speak_spelling = speech.speakSpelling
				speech.speakSpelling = self._custom_speak_spelling

		# Śledzenie ruchu wirtualnego kursora w PDF / BrowseMode (R07)
		try:
			import cursorManager
			if _orig_cursor_set_selection is None and hasattr(cursorManager, "CursorManager"):
				_orig_cursor_set_selection = cursorManager.CursorManager._set_selection
				plugin_ref = self

				def _hooked_set_selection(cm_self, info, *args, **kwargs):
					res = _orig_cursor_set_selection(cm_self, info, *args, **kwargs)
					try:
						plugin_ref._on_virtual_selection_changed(cm_self, info)
					except Exception:
						pass
					return res

				cursorManager.CursorManager._set_selection = _hooked_set_selection
		except Exception as ex:
			log.debug(f"docListNavigator: hook CursorManager._set_selection error: {ex}")

		# Inicjalizacja modułu aktualizacji i opóźnione sprawdzenie w tle
		self._updater = AddonUpdaterEngine(
			addon_name=ADDON_NAME,
			addon_title=ADDON_TITLE,
			current_version=ADDON_VERSION,
			addon_dir=ADDON_DIR,
			config_section=CONFIG_SECTION
		)
		try:
			self._startup_update_timer = wx.CallLater(12000, self._check_updates_auto)
		except Exception:
			pass

		log.info(f"docListNavigator v{ADDON_VERSION}: Dodatek pomyślnie załadowany i zainicjalizowany.")

	def _check_updates_auto(self):
		conf = config.conf.get(CONFIG_SECTION, {})
		if not conf.get("autoCheckUpdates", True):
			return
		last_time = conf.get("lastUpdateCheckTime", 0.0)
		if time.time() - last_time < 86400:
			return
		self._updater.check_for_updates(manual=False)

	def terminate(self):
		global _orig_speak, _orig_manager_speak, _orig_speak_spelling, _orig_cursor_set_selection
		try:
			if getattr(self, "_startup_update_timer", None) is not None:
				self._startup_update_timer.Stop()
				self._startup_update_timer = None
		except Exception:
			pass

		try:
			if getattr(self, "_filter_registered", False) and hasattr(speech, "extensions") and hasattr(speech.extensions, "filter_speechSequence"):
				speech.extensions.filter_speechSequence.unregister(self._filter_speech_sequence)
				self._filter_registered = False
		except Exception:
			pass

		if _orig_speak is not None:
			if hasattr(speech, "speech") and hasattr(speech.speech, "speak"):
				speech.speech.speak = _orig_speak
			if hasattr(speech, "speak"):
				speech.speak = _orig_speak
			try:
				if hasattr(speech, "sayAll") and getattr(speech.sayAll, "SayAllHandler", None) is not None:
					swp = getattr(speech.sayAll.SayAllHandler, "_speechWithoutPausesInstance", None)
					if swp is not None and hasattr(swp, "speak"):
						swp.speak = _orig_speak
			except Exception:
				pass
			_orig_speak = None

		if _orig_manager_speak is not None:
			try:
				if hasattr(speech, "speech") and hasattr(speech.speech, "_manager"):
					speech.speech._manager.speak = _orig_manager_speak
			except Exception:
				pass
			_orig_manager_speak = None

		if _orig_speak_spelling is not None:
			if hasattr(speech, "speech") and hasattr(speech.speech, "speakSpelling"):
				speech.speech.speakSpelling = _orig_speak_spelling
			if hasattr(speech, "speakSpelling"):
				speech.speakSpelling = _orig_speak_spelling
			_orig_speak_spelling = None

		if _orig_cursor_set_selection is not None:
			try:
				import cursorManager
				if hasattr(cursorManager, "CursorManager"):
					cursorManager.CursorManager._set_selection = _orig_cursor_set_selection
			except Exception:
				pass
			_orig_cursor_set_selection = None

		try:
			gui.settingsDialogs.NVDASettingsDialog.categoryClasses.remove(DocListNavigatorSettingsPanel)
		except Exception:
			pass
		super().terminate()

	# --------------------------------------------------------------------------
	# DETEKCJA AKTYWNEJ APLIKACJI
	# --------------------------------------------------------------------------

	def _is_word_active(self) -> bool:
		"""Sprawdza, czy aktywną aplikacją jest Microsoft Word."""
		try:
			focus = api.getFocusObject()
			if not focus:
				return False
			app_name = (getattr(focus.appModule, "appName", "") or "").lower()
			if app_name == "winword":
				return True
			window_class = (getattr(focus, "windowClassName", "") or "").lower()
			if "_wwg" in window_class or "_wwb" in window_class or "opusapp" in window_class:
				return True
			return False
		except Exception:
			return False

	def _is_acrobat_active(self) -> bool:
		"""Sprawdza, czy aktywną aplikacją jest Adobe Acrobat Reader."""
		try:
			focus = api.getFocusObject()
			if not focus:
				return False
			app_name = (getattr(focus.appModule, "appName", "") or "").lower()
			if app_name in ("acrord32", "acrobat", "acrocef"):
				return True
			return False
		except Exception:
			return False

	def _is_target_application_active(self) -> bool:
		"""Sprawdza, czy aktywną aplikacją jest MS Word lub Adobe Acrobat Reader."""
		return self._is_word_active() or self._is_acrobat_active()

	def _filter_speech_sequence(self, speechSequence, *args, **kwargs):
		"""
		Wspólny filtr sekwencji mowy dla wszystkich ścieżek odczytu (w tym SayAll),
		chroniący tryb literowania i odczyt pojedynczych znaków (R01, R02).
		"""
		if getattr(self, "_in_spelling_mode", 0) > 0:
			return speechSequence

		conf = config.conf.get(CONFIG_SECTION, {})
		if not conf.get("enableRomanNumerals", True):
			return speechSequence

		scope = conf.get("romanNumeralsScope", "targetApps")
		should_transform = (scope == "global") or self._is_target_application_active()
		if not should_transform or not speechSequence:
			return speechSequence

		newSeq = []
		in_char_mode = False
		for item in speechSequence:
			if isinstance(item, str):
				if in_char_mode or len(item.strip()) <= 1:
					newSeq.append(item)
				else:
					newSeq.append(transform_roman_text(item))
			else:
				state_val = getattr(item, "state", None)
				if type(item).__name__ == "CharacterModeCommand" or isinstance(state_val, bool):
					in_char_mode = bool(state_val)
				newSeq.append(item)
		return newSeq

	def _custom_speak(self, speechSequence, *args, **kwargs):
		"""
		Filtruje sekwencję mowy, zamieniając cyfry rzymskie na postać 'rzymskie <liczba>'
		zgodnie z konfiguracją użytkownika.
		"""
		speechSequence = self._filter_speech_sequence(speechSequence)
		if _orig_speak is not None:
			return _orig_speak(speechSequence, *args, **kwargs)
		return None

	def _custom_manager_speak(self, speechSequence, *args, **kwargs):
		speechSequence = self._filter_speech_sequence(speechSequence)
		if _orig_manager_speak is not None:
			return _orig_manager_speak(speechSequence, *args, **kwargs)
		return None

	def _custom_speak_spelling(self, *args, **kwargs):
		self._in_spelling_mode = getattr(self, "_in_spelling_mode", 0) + 1
		try:
			if _orig_speak_spelling is not None:
				return _orig_speak_spelling(*args, **kwargs)
		finally:
			self._in_spelling_mode = max(0, getattr(self, "_in_spelling_mode", 1) - 1)

	# --------------------------------------------------------------------------
	# ODGŁOSY DŹWIĘKOWE (TONES)
	# --------------------------------------------------------------------------

	def _play_nav_tone(self, tone_type: str):
		conf = config.conf.get(CONFIG_SECTION, {})
		mode = conf.get("levelAnnouncementMode", "both")
		if mode not in ("tone", "both"):
			return

		vol = conf.get("soundVolume", 80)
		if vol <= 0:
			return

		try:
			if tone_type == "deeper":   # C5 -> E5
				tones.beep(523, 60, left=vol, right=vol)
				tones.beep(659, 60, left=vol, right=vol)
			elif tone_type == "higher": # E5 -> C5
				tones.beep(659, 60, left=vol, right=vol)
				tones.beep(523, 60, left=vol, right=vol)
			elif tone_type == "same":    # Krótki ton potwierdzenia
				tones.beep(880, 45, left=vol, right=vol)
			elif tone_type == "boundary": # Niski ton granicy (początek/koniec)
				tones.beep(220, 65, left=vol, right=vol)
		except Exception as e:
			log.debug(f"docListNavigator: błąd odtwarzania dźwięku: {e}")

	# --------------------------------------------------------------------------
	# INTEGRACJA Z MICROSOFT WORD (COM / ACCESSIBLE OBJECT)
	# --------------------------------------------------------------------------

	def _get_word_objects(self):
		"""
		Pobiera obiekty Worda (word_app, doc, sel) z użyciem kaskady 3 metod:
		1. Bezpośrednio z właściwości NVDAObject (focus, jego rodzice)
		2. Za pośrednictwem oleacc.AccessibleObjectFromWindow z OBJID_NATIVEOM (-16)
		3. comtypes.client.GetActiveObject("Word.Application")
		"""
		focus = api.getFocusObject()

		# Metoda 1: Właściwości natywne obiektu w NVDA
		curr = focus
		for _ in range(5):
			if not curr:
				break
			app = getattr(curr, "WinwordApplicationObject", None)
			doc = getattr(curr, "WinwordDocumentObject", None)
			sel = getattr(curr, "WinwordSelectionObject", None)
			win_obj = getattr(curr, "WinwordWindowObject", None)
			if win_obj:
				if not app:
					app = getattr(win_obj, "application", None) or getattr(win_obj, "Application", None)
				if not doc:
					doc = getattr(win_obj, "document", None) or getattr(win_obj, "Document", None)
				if not sel:
					sel = getattr(win_obj, "selection", None) or getattr(win_obj, "Selection", None)
			if doc or app:
				if not sel and app:
					try:
						sel = getattr(app, "Selection", None)
					except Exception:
						pass
				return app, doc, sel
			curr = getattr(curr, "parent", None)

		# Metoda 2: AccessibleObjectFromWindow na oknie _WwG (R17, R18)
		try:
			import ctypes
			from ctypes import wintypes
			import oleacc
			import comtypes.automation
			import comtypes.client.dynamic
			import winUser

			hwnds_to_check = []
			if focus and getattr(focus, "windowHandle", 0):
				hwnds_to_check.append(focus.windowHandle)
			fg = winUser.getForegroundWindow()
			if fg and fg not in hwnds_to_check:
				hwnds_to_check.append(fg)

			WNDENUMPROC = (
				getattr(winUser, "WNDENUMPROC", None)
				or getattr(winUser, "_WNDENUMPROC", None)
				or ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
			)

			def _enum_child_proc(h, l):
				try:
					cls_name = winUser.getClassName(h).lower()
					if "_wwg" in cls_name or "_wwb" in cls_name:
						hwnds_to_check.append(h)
				except Exception:
					pass
				return True

			enum_cb = WNDENUMPROC(_enum_child_proc)
			user32_mod = getattr(winUser, "user32", None) or ctypes.windll.user32
			for ph in list(hwnds_to_check):
				try:
					user32_mod.EnumChildWindows(ph, enum_cb, 0)
				except Exception:
					pass

			for h in hwnds_to_check:
				try:
					cls_name = winUser.getClassName(h).lower()
					if "_ww" in cls_name:
						pacc = oleacc.AccessibleObjectFromWindow(h, -16, interface=comtypes.automation.IDispatch)
						if pacc:
							win_obj = comtypes.client.dynamic.Dispatch(pacc)
							app = getattr(win_obj, "application", None) or getattr(win_obj, "Application", None)
							doc = getattr(win_obj, "document", None) or getattr(win_obj, "Document", None)
							sel = getattr(win_obj, "selection", None) or getattr(win_obj, "Selection", None)
							if not sel and app:
								try:
									sel = getattr(app, "Selection", None)
								except Exception:
									pass
							if doc or app:
								return app, doc, sel
				except Exception:
					continue
		except Exception as ex:
			log.debug(f"docListNavigator: AccessibleObjectFromWindow fallback error: {ex}")

		# Metoda 3: comtypes.client.GetActiveObject
		try:
			import comtypes.client
			app = comtypes.client.GetActiveObject("Word.Application")
			if app:
				doc = getattr(app, "ActiveDocument", None)
				sel = getattr(app, "Selection", None)
				return app, doc, sel
		except Exception:
			pass

		return None, None, None

	def _compute_word_cache_key(self, doc, doc_id: str, content_end: int):
		"""Buduje odcisk dokumentu uwzględniający treść i formatowanie list/nagłówków (R04)."""
		content_text = ""
		try:
			content_rng = getattr(doc, "Content", None)
			if content_rng is not None:
				content_text = str(getattr(content_rng, "Text", "") or "")
		except Exception:
			pass

		para_sig = []
		try:
			paragraphs = getattr(doc, "Paragraphs", None)
			p_count = int(getattr(paragraphs, "Count", 0) or 0)
			if p_count > 0 and hasattr(paragraphs, "__getitem__"):
				sample_indices = list(range(min(p_count, 32)))
				if p_count > 32:
					sample_indices.extend(range(max(32, p_count - 32), p_count))
				for idx in sample_indices:
					try:
						p = paragraphs[idx]
					except Exception:
						try:
							p = paragraphs[idx + 1]
						except Exception:
							continue
					rng = getattr(p, "Range", None)
					if rng is None:
						continue
					lf = getattr(rng, "ListFormat", None)
					para_sig.append((
						str(getattr(rng, "Text", "") or ""),
						int(getattr(p, "OutlineLevel", 10) or 10),
						float(getattr(p, "LeftIndent", 0.0) or 0.0),
						int(getattr(lf, "ListType", 0) or 0) if lf is not None else 0,
						str(getattr(lf, "ListString", "") or "") if lf is not None else "",
						int(getattr(lf, "ListLevelNumber", -1) or -1) if lf is not None else -1,
					))
		except Exception:
			pass

		return (doc_id, content_end, content_text, tuple(para_sig))

	def _collect_word_document_items(self, word_app, doc, sel) -> tuple[list[DocumentItem], int]:
		"""
		Pobiera strukturę dokumentu z Worda z pełnymi metadanymi list i nagłówków
		oraz bezpiecznym fallbackiem tekstowym (R03, R04, R05, R09).
		"""
		items = []
		cur_idx = -1
		if not doc and word_app:
			try:
				doc = word_app.ActiveDocument
			except Exception:
				pass
		if not doc:
			return items, cur_idx

		cur_para_start = -1
		if sel:
			try:
				cur_para_start = int(sel.Range.Start)
			except Exception:
				pass

		now = time.time()
		doc_name = ""
		doc_id = ""
		content_end = -1
		try:
			doc_name = str(getattr(doc, "Name", "") or "")
			doc_id = str(getattr(doc, "FullName", "") or doc_name or "")
			content_end = int(doc.Content.End)
		except Exception:
			pass

		cache_key = self._compute_word_cache_key(doc, doc_id, content_end)

		# 1. Sprawdź pamięć podręczną (cache) — jeśli ten sam dokument, brak zmian treści/formatowania i upłynęło < 30 s
		if self._word_cache_items and getattr(self, "_word_cache_key", None) == cache_key and (now - self._word_cache_time) < 30.0:
			items = self._word_cache_items
		else:
			# 2. Pobieranie akapitów Worda z metadanymi (listy natywne, style, wcięcia) — bez sztucznego limitu 2500 (R03)
			used_paragraphs = False
			try:
				paragraphs = doc.Paragraphs
				p_count = paragraphs.Count
				if p_count > 0:
					for p in paragraphs:
						rng = p.Range
						txt = str(rng.Text or "").strip()
						p_start = int(rng.Start)
						p_end = int(rng.End)

						outline_lvl = 10
						try:
							outline_lvl = int(p.OutlineLevel)
						except Exception:
							pass

						list_type = 0
						list_string = ""
						list_level = -1
						try:
							lf = rng.ListFormat
							list_type = int(lf.ListType)
							if list_type > 0:
								list_string = str(lf.ListString or "")
								list_level = int(lf.ListLevelNumber)
						except Exception:
							pass

						left_indent = 0.0
						try:
							left_indent = float(p.LeftIndent)
						except Exception:
							pass

						if not txt and not list_string:
							continue

						lvl, marker = classify_paragraph(
							txt,
							left_indent_pt=left_indent,
							outline_level=outline_lvl,
							list_level=list_level,
							list_string=list_string,
							list_type=list_type
						)
						if lvl != LogicalLevel.BODY:
							items.append(DocumentItem(
								index=len(items),
								text=f"{list_string} {txt}".strip() if list_string else txt,
								level=lvl,
								marker=marker,
								raw_obj=None,
								range_start=p_start,
								range_end=p_end,
								app_source="word",
								list_level=list_level
							))
					used_paragraphs = True
			except Exception as ex:
				log.debug(f"docListNavigator: błąd odczytu doc.Paragraphs: {ex}")
				items = []
				used_paragraphs = False

			if not used_paragraphs:
				# Odrzucamy częściowy wynik i stosujemy fallback na cały tekst dokumentu (R05)
				items = []
				full_text = ""
				try:
					content_rng = doc.Content
					full_text = str(getattr(content_rng, "Text", "") or "")
				except Exception as ex:
					log.debug(f"docListNavigator: błąd pobierania doc.Content.Text: {ex}")

				if full_text:
					offset = 0
					raw_paras = full_text.split('\r')
					for raw_p in raw_paras:
						p_len = len(raw_p)
						p_start = offset
						p_end = offset + p_len + 1  # +1 dla separatora \r
						offset = p_end

						txt = raw_p.strip()
						if not txt:
							continue

						lvl, marker = classify_paragraph(txt)
						if lvl != LogicalLevel.BODY:
							items.append(DocumentItem(
								index=len(items),
								text=txt,
								level=lvl,
								marker=marker,
								raw_obj=None,
								range_start=p_start,
								range_end=p_end,
								app_source="word"
							))

			self._build_item_hierarchy(items)
			self._word_cache_items = items
			self._word_cache_doc = doc_name
			self._word_cache_key = cache_key
			self._word_cache_time = now

		# 3. Wyznaczenie indeksu bieżącego elementu na podstawie aktualnej pozycji kursora (R09: -1 przed pierwszym elementem)
		if items and cur_para_start != -1:
			for i, it in enumerate(items):
				if it.range_start <= cur_para_start < it.range_end:
					cur_idx = i
					break
				elif cur_para_start >= it.range_end:
					cur_idx = i

		if items and cur_idx >= len(items):
			cur_idx = len(items) - 1
		return items, cur_idx

	# --------------------------------------------------------------------------
	# INTEGRACJA Z ADOBE ACROBAT READER (VIRTUAL BUFFER)
	# --------------------------------------------------------------------------

	def _collect_acrobat_document_items(self, focus_obj) -> tuple[list[DocumentItem], int]:
		"""Pobiera logiczne punkty z wirtualnego bufora Adobe Acrobat."""
		items = []
		cur_idx = -1
		try:
			ti = getattr(focus_obj, "treeInterceptor", None)
			if not ti:
				return items, -1

			caret_info = ti.makeTextInfo(textInfos.POSITION_CARET)
			all_info = ti.makeTextInfo(textInfos.POSITION_FIRST)
			all_info.expand(textInfos.UNIT_PARAGRAPH)

			while True:
				t = (all_info.text or "").strip()
				if t:
					lvl, marker = classify_paragraph(t)
					if lvl != LogicalLevel.BODY:
						item = DocumentItem(
							index=len(items),
							text=t,
							level=lvl,
							marker=marker,
							raw_obj=all_info.copy(),
							range_start=-1,
							range_end=-1,
							app_source="acrobat"
						)
						try:
							if caret_info.compareEndPoints(all_info, "startToStart") >= 0:
								cur_idx = len(items)
						except Exception:
							pass
						items.append(item)

				if all_info.move(textInfos.UNIT_PARAGRAPH, 1) <= 0:
					break
				all_info.expand(textInfos.UNIT_PARAGRAPH)

		except Exception as ex:
			log.error(f"docListNavigator: błąd zbierania punktów Acrobat: {ex}")

		self._build_item_hierarchy(items)
		if items and cur_idx >= len(items):
			cur_idx = len(items) - 1
		return items, cur_idx

	def _build_item_hierarchy(self, items: list[DocumentItem]):
		"""Buduje relacje rodzic-dziecko na podstawie poziomów logicznych oraz numeruje punkty i tirety (R20, R22, R23)."""
		stack = []  # stos (level, index)
		for it in items:
			while stack and stack[-1][0] >= it.level:
				stack.pop()
			if stack:
				parent_idx = stack[-1][1]
				it.parent_index = parent_idx
				items[parent_idx].children_indices.append(it.index)
			stack.append((it.level, it.index))

		def _assign_sibling_markers(sibling_indices: list[int]):
			level_counts = {}
			for ch_idx in sibling_indices:
				ch = items[ch_idx]
				cnt = level_counts.get(ch.level, 0) + 1
				level_counts[ch.level] = cnt
				ch.sibling_index = cnt

				# Jeśli to tiret: przypisz nazwę porządkową (np. tiret pierwszy, tiret drugie)
				if ch.level == LogicalLevel.TIRET:
					word = TIRET_ORDINALS_PL.get(cnt, f"{cnt}.")
					ch.marker = f"tiret {word}"
				# Jeśli to litera bez jednoznacznego znacznika w tekście (np. Zadanie) — obsługuje >26 elementów (R23):
				elif ch.level == LogicalLevel.LITERA and (not ch.marker or ch.marker == "litera"):
					let_seq = _index_to_letters(cnt - 1)
					ch.marker = f"litera {let_seq})"
				# Jeśli to punkt bez jednoznacznego znacznika w tekście (np. Obszar):
				elif ch.level == LogicalLevel.PUNKT and (not ch.marker or ch.marker == "pkt"):
					ch.marker = f"pkt {cnt})"
				# Jeśli to ustęp bez jednoznacznego znacznika w tekście (np. Moduł):
				elif ch.level == LogicalLevel.USTEP and (not ch.marker or ch.marker == "ustęp"):
					ch.marker = f"ustęp {cnt}."

		# 1. Numeracja porządkowa elementów głównych bez rodzica (R20)
		root_indices = [it.index for it in items if it.parent_index == -1]
		if root_indices:
			_assign_sibling_markers(root_indices)

		# 2. Numeracja porządkowa dzieci dla każdego elementu nadrzędnego
		for it in items:
			if it.children_indices:
				_assign_sibling_markers(it.children_indices)

	# --------------------------------------------------------------------------
	# NAWIGACJA I SKOKI DO ELEMENTÓW
	# --------------------------------------------------------------------------

	def _jump_to_item(self, item: DocumentItem):
		"""Przenosi kursor w aplikacji do wskazanego akapitu."""
		try:
			# Adobe Acrobat Reader / wirtualny bufor — synchronizacja przez selekcję treeInterceptora (R06)
			if getattr(item, "app_source", "") == "acrobat" or hasattr(item.raw_obj, "updateCaret"):
				if item.raw_obj is not None:
					caret_info = item.raw_obj.copy() if hasattr(item.raw_obj, "copy") else item.raw_obj
					if hasattr(caret_info, "collapse"):
						try:
							caret_info.collapse()
						except Exception:
							pass
					focus = api.getFocusObject()
					ti = getattr(caret_info, "obj", None) or getattr(focus, "treeInterceptor", None)
					if ti is not None and hasattr(ti, "_set_selection"):
						ti._set_selection(caret_info)
					elif ti is not None and hasattr(ti, "selection"):
						try:
							ti.selection = caret_info
						except Exception:
							if hasattr(caret_info, "updateCaret"):
								caret_info.updateCaret()
					elif hasattr(caret_info, "updateCaret"):
						caret_info.updateCaret()

					if ti is not None:
						try:
							speech.speakTextInfo(item.raw_obj, reason=controlTypes.OutputReason.CARET)
						except Exception:
							pass
					ui.message(item.display_label)
					return

			# Microsoft Word (szybki skok bezpośrednio przez pozycję zakresu)
			if getattr(item, "app_source", "word") == "word" and getattr(item, "range_start", -1) >= 0:
				word_app, doc, sel = self._get_word_objects()
				if doc:
					try:
						target_rng = doc.Range(item.range_start, item.range_start)
						target_rng.Select()
						ui.message(item.display_label)
						return
					except Exception:
						pass

			if hasattr(item.raw_obj, "Range"):
				rng = item.raw_obj.Range
				rng.Select()
				try:
					word_app, doc, sel = self._get_word_objects()
					if sel:
						sel.Collapse(1)  # 1 = wdCollapseStart
					else:
						rng.Collapse(1)
				except Exception:
					pass
				ui.message(item.display_label)
				return

		except Exception as ex:
			log.error(f"docListNavigator: błąd skoku do punktu: {ex}")
			ui.message(f"Błąd nawigacji: {ex}")

	def _get_document_items_and_cur_idx(self) -> tuple[list[DocumentItem], int]:
		"""Zwraca elementy struktury i aktualną pozycję kursora w aktywnym dokumencie."""
		if self._is_word_active():
			word_app, doc, sel = self._get_word_objects()
			if doc or word_app:
				return self._collect_word_document_items(word_app, doc, sel)
			else:
				log.debug("docListNavigator: aktywne okno Word, lecz nie udało się uzyskać obiektów COM.")
		elif self._is_acrobat_active():
			focus = api.getFocusObject()
			return self._collect_acrobat_document_items(focus)
		return [], -1

	# --------------------------------------------------------------------------
	# SKRYPTY GESTÓW (SKRÓTY KLAWISZOWE)
	# --------------------------------------------------------------------------

	@script(
		description="Odczytuje pełną ścieżkę hierarchiczną bieżącego punktu (np. Rozdział VI > ustęp 1 > litera a). Podwójne wciśnięcie kopiuje do schowka.",
		gesture="kb:NVDA+alt+l"
	)
	def script_speakBreadcrumb(self, gesture):
		if not self._is_target_application_active():
			gesture.send()
			return

		items, cur_idx = self._get_document_items_and_cur_idx()
		if not items or cur_idx >= len(items):
			ui.message("W bieżącym dokumencie nie wykryto elementów list ani nagłówków.")
			return
		if cur_idx < 0:
			ui.message("Kursor znajduje się przed pierwszym punktem lub nagłówkiem dokumentu.")
			return

		path_items = []
		curr = items[cur_idx]
		while curr:
			if curr.marker:
				path_items.append(curr.marker.strip())
			else:
				lbl = LEVEL_SHORT_NAMES.get(curr.level, "")
				path_items.append(lbl)
			if curr.parent_index != -1 and curr.parent_index < len(items):
				curr = items[curr.parent_index]
			else:
				break

		path_items.reverse()
		breadcrumb_str = " > ".join(path_items)
		cur_item = items[cur_idx]

		now = time.time()
		is_double = (now - self._last_breadcrumb_press) < 0.5
		self._last_breadcrumb_press = now

		if is_double:
			full_copy = f"{breadcrumb_str}\n{cur_item.text}"
			if api.copyToClip(full_copy):
				ui.message(f"Skopiowano do schowka: {breadcrumb_str}")
		else:
			ui.message(f"{breadcrumb_str}: {cur_item.text[:60]}")

	@script(
		description="Przechodzi do następnego punktu na tym samym poziomie logicznym.",
		gesture="kb:NVDA+alt+downArrow"
	)
	def script_nextSameLevel(self, gesture):
		if not self._is_target_application_active():
			gesture.send()
			return
		self._navigate_same_level(direction=1, gesture=gesture)

	@script(
		description="Przechodzi do poprzedniego punktu na tym samym poziomie logicznym.",
		gesture="kb:NVDA+alt+upArrow"
	)
	def script_prevSameLevel(self, gesture):
		if not self._is_target_application_active():
			gesture.send()
			return
		self._navigate_same_level(direction=-1, gesture=gesture)

	def _navigate_same_level(self, direction: int, gesture=None):
		if not self._is_target_application_active():
			if gesture:
				gesture.send()
			else:
				ui.message("Nawigator list: otwórz dokument w programie MS Word lub Adobe Acrobat Reader.")
			return

		items, cur_idx = self._get_document_items_and_cur_idx()
		if not items:
			ui.message("W bieżącym dokumencie nie wykryto elementów list ani nagłówków.")
			return

		if cur_idx < 0:
			if direction > 0:
				self._play_nav_tone("same")
				self._jump_to_item(items[0])
			else:
				self._play_nav_tone("boundary")
				ui.message("Kursor znajduje się przed pierwszym punktem dokumentu.")
			return

		cur_item = items[cur_idx]
		target = None

		if direction > 0:
			for i in range(cur_idx + 1, len(items)):
				it = items[i]
				if it.level < cur_item.level:
					break
				if it.level == cur_item.level:
					target = it
					break
		else:
			for i in range(cur_idx - 1, -1, -1):
				it = items[i]
				if it.level < cur_item.level:
					break
				if it.level == cur_item.level:
					target = it
					break

		if target:
			self._play_nav_tone("same")
			self._jump_to_item(target)
		else:
			self._play_nav_tone("boundary")
			edge = "ostatni" if direction > 0 else "pierwszy"
			ui.message(f"To jest {edge} punkt na poziomie {LEVEL_SHORT_NAMES.get(cur_item.level, '')}.")

	@script(
		description="Przechodzi do elementu nadrzędnego (poziom wyżej w hierarchii).",
		gesture="kb:NVDA+alt+leftArrow"
	)
	def script_jumpParent(self, gesture):
		if not self._is_target_application_active():
			gesture.send()
			return

		items, cur_idx = self._get_document_items_and_cur_idx()
		if not items:
			ui.message("W bieżącym dokumencie nie wykryto elementów list ani nagłówków.")
			return
		if cur_idx < 0:
			self._play_nav_tone("boundary")
			ui.message("Kursor znajduje się przed pierwszym punktem dokumentu — brak elementu nadrzędnego.")
			return

		cur_item = items[cur_idx]
		if cur_item.parent_index != -1 and cur_item.parent_index < len(items):
			parent_item = items[cur_item.parent_index]
			self._play_nav_tone("higher")
			self._jump_to_item(parent_item)
		else:
			self._play_nav_tone("boundary")
			ui.message(f"Brak elementu nadrzędnego dla {LEVEL_SHORT_NAMES.get(cur_item.level, '')} — to jest najwyższy poziom.")

	@script(
		description="Przechodzi do pierwszego podpunktu (poziom niżej w hierarchii).",
		gesture="kb:NVDA+alt+rightArrow"
	)
	def script_jumpFirstChild(self, gesture):
		if not self._is_target_application_active():
			gesture.send()
			return

		items, cur_idx = self._get_document_items_and_cur_idx()
		if not items:
			ui.message("W bieżącym dokumencie nie wykryto elementów list ani nagłówków.")
			return
		if cur_idx < 0:
			self._play_nav_tone("boundary")
			ui.message("Kursor znajduje się przed pierwszym punktem dokumentu.")
			return

		cur_item = items[cur_idx]
		if cur_item.children_indices:
			child_item = items[cur_item.children_indices[0]]
			self._play_nav_tone("deeper")
			self._jump_to_item(child_item)
		else:
			self._play_nav_tone("boundary")
			ui.message("Brak podpunktów dla tego elementu.")

	@script(
		description="Wyświetla okno drzewa struktury dokumentu z możliwością szybkiego wyszukiwania i przechodzenia.",
		gesture="kb:NVDA+alt+f7"
	)
	def script_showStructureTree(self, gesture):
		if not self._is_target_application_active():
			gesture.send()
			return

		items, cur_idx = self._get_document_items_and_cur_idx()
		if not items:
			ui.message("W bieżącym dokumencie nie znaleziono żadnych punktów ani nagłówków.")
			return

		def _show():
			def _on_select(target_item):
				wx.CallAfter(self._jump_to_item, target_item)

			dlg = DocumentStructureDialog(
				parent=gui.mainFrame,
				title="Struktura dokumentu — Nawigator list",
				items=items,
				current_index=cur_idx,
				on_select_callback=_on_select
			)
			gui.mainFrame.prePopup()
			try:
				dlg.ShowModal()
				dlg.Destroy()
			finally:
				gui.mainFrame.postPopup()

		wx.CallAfter(_show)

	@script(
		description="Szybko włącza lub wyłącza automatyczną sygnalizację zmiany poziomów podczas czytania strzałkami.",
		gesture="kb:NVDA+control+shift+l"
	)
	def script_toggleAutoLevel(self, gesture):
		conf = config.conf[CONFIG_SECTION]
		new_state = not conf.get("autoAnnounceLevel", True)
		conf["autoAnnounceLevel"] = new_state
		state_str = "włączone" if new_state else "wyłączone"
		ui.message(f"Automatyczne ogłaszanie poziomów: {state_str}")

	@script(
		description="Szybko włącza lub wyłącza wymowę cyfr rzymskich.",
		gesture="kb:NVDA+control+shift+r"
	)
	def script_toggleRomanNumerals(self, gesture):
		conf = config.conf[CONFIG_SECTION]
		new_state = not conf.get("enableRomanNumerals", True)
		conf["enableRomanNumerals"] = new_state
		state_str = "włączona" if new_state else "wyłączona"
		ui.message(f"Wymowa cyfr rzymskich: {state_str}")

	@script(
		description="Wyświetla podręczny spis skrótów i pomoc w buforze przeglądania NVDA.",
		gesture="kb:NVDA+control+shift+h"
	)
	def script_showHelp(self, gesture):
		help_text = (
			"NAWIGATOR LIST I CYFR RZYMSKICH — SKRÓTY KLAWISZOWE\n"
			+ "=" * 65 + "\n\n"
			"NAWIGACJA HIERARCHICZNA W DOKUMENTACH (WORD I ACROBAT):\n"
			"  NVDA + Alt + L                 - Odczytuje pełną ścieżkę pozycji (np. Moduł I > Obszar A > Zadanie 1)\n"
			"                                   (Dwukrotne szybkie wciśnięcie kopiuje pełną ścieżkę do schowka)\n"
			"  NVDA + Alt + Strzałka w dół   - Skok do NASTĘPNEGO punktu na tym samym poziomie\n"
			"  NVDA + Alt + Strzałka w górę  - Skok do POPRZEDNIEGO punktu na tym samym poziomie\n"
			"  NVDA + Alt + Strzałka w lewo  - Skok do ELEMENTU NADRZĘDNEGO (poziom wyżej)\n"
			"  NVDA + Alt + Strzałka w prawo - Skok do PIERWSZEGO PODPUNKTU (poziom niżej)\n"
			"  NVDA + Alt + F7                - Okno drzewa struktury dokumentu z wyszukiwarką i skokiem na Enter\n\n"
			"PRZEŁĄCZNIKI TRYBU:\n"
			"  NVDA + Ctrl + Shift + L        - Włączenie/wyłączenie automatycznego ogłaszania zmiany poziomów\n"
			"  NVDA + Ctrl + Shift + R        - Włączenie/wyłączenie wymowy cyfr rzymskich\n"
			"  NVDA + Ctrl + Shift + H        - Wyświetlenie tej pomocy podręcznej\n"
			"  F1                             - Pomoc kontekstowa w oknach dialogowych dodatku\n\n"
			"WYMOWA CYFR RZYMSKICH:\n"
			"  Dodatek automatycznie wymawia zapisy cyfrowe w systemie rzymskim (np. 'III', 'IV', 'VI')\n"
			"  w sposób naturalny: 'rzymskie trzy', 'rzymskie cztery', 'w module rzymskie dwa',\n"
			"  zabezpieczając przed błędnym odczytem zwykłego spójnika 'i'.\n"
		)
		ui.browseableMessage(help_text, "Pomoc: Nawigator list i cyfr rzymskich")

	# --------------------------------------------------------------------------
	# ŚLEDZENIE ZMIANY POZIOMU PRZY NORMALNYM RUCHU STRZAŁKAMI (R07, R08)
	# --------------------------------------------------------------------------

	def _extract_paragraph_metadata(self, obj, info) -> tuple[float, int, int, str, int]:
		"""Pobiera metadane natywnej listy i stylu akapitu z TextInfo, obiektu NVDA lub COM Worda (R08)."""
		left_indent = 0.0
		outline_lvl = 10
		list_level = -1
		list_string = ""
		list_type = 0

		rng = (
			getattr(info, "_rangeObj", None)
			or getattr(info, "Range", None)
			or getattr(info, "rangeObj", None)
		)
		if rng is None and hasattr(info, "ListFormat"):
			rng = info
		if rng is None and obj is not None:
			sel_obj = getattr(obj, "WinwordSelectionObject", None)
			if sel_obj is not None:
				rng = getattr(sel_obj, "Range", None)
			if rng is None and hasattr(obj, "ListFormat"):
				rng = obj
		if rng is None:
			try:
				if hasattr(self, "_get_word_objects"):
					_, _, sel_obj = self._get_word_objects()
					if sel_obj is not None:
						rng = getattr(sel_obj, "Range", None)
			except Exception:
				pass

		for src in (rng, info, obj):
			if src is None:
				continue
			if list_type == 0:
				try:
					lf = getattr(src, "ListFormat", None)
					if lf is not None:
						lt = int(getattr(lf, "ListType", 0) or 0)
						if lt > 0:
							list_type = lt
							list_string = str(getattr(lf, "ListString", "") or "")
							list_level = int(getattr(lf, "ListLevelNumber", -1) or -1)
				except Exception:
					pass

			p_src = src
			try:
				paras = getattr(src, "Paragraphs", None)
				if paras is not None:
					if hasattr(paras, "__getitem__"):
						try:
							p_src = paras[0]
						except Exception:
							p_src = paras[1]
					elif callable(paras):
						p_src = paras(1)
			except Exception:
				pass

			if outline_lvl == 10:
				try:
					ol = getattr(p_src, "OutlineLevel", None)
					if ol is not None:
						outline_lvl = int(ol)
				except Exception:
					pass
			if left_indent == 0.0:
				try:
					li = getattr(p_src, "LeftIndent", None)
					if li is not None:
						left_indent = float(li)
				except Exception:
					pass

		return left_indent, outline_lvl, list_level, list_string, list_type

	def _announce_level_for_info(self, obj, info):
		conf = config.conf.get(CONFIG_SECTION, {})
		if not conf.get("autoAnnounceLevel", True) or not self._is_target_application_active():
			return

		p_info = info.copy() if hasattr(info, "copy") else info
		if hasattr(p_info, "expand"):
			p_info.expand(textInfos.UNIT_PARAGRAPH)
		txt = (getattr(p_info, "text", "") or "").strip()
		left_indent, outline_lvl, list_level, list_string, list_type = self._extract_paragraph_metadata(obj, p_info)

		if not txt and not list_string:
			return

		lvl, marker = classify_paragraph(
			txt,
			left_indent_pt=left_indent,
			outline_level=outline_lvl,
			list_level=list_level,
			list_string=list_string,
			list_type=list_type
		)

		if lvl != LogicalLevel.BODY and lvl != self._last_announced_level:
			prev_lvl = self._last_announced_level
			self._last_announced_level = lvl
			mode = conf.get("levelAnnouncementMode", "both")

			if mode in ("tone", "both"):
				if prev_lvl != -1 and lvl > prev_lvl:
					self._play_nav_tone("deeper")
				elif prev_lvl != -1 and lvl < prev_lvl:
					self._play_nav_tone("higher")
				else:
					self._play_nav_tone("same")

			if mode in ("speech", "both"):
				if marker:
					ui.message(marker)
				else:
					lvl_name = LEVEL_SHORT_NAMES.get(lvl, "")
					ui.message(lvl_name)

	def _on_virtual_selection_changed(self, cm_obj, info):
		"""Obsługuje ruch wirtualnego kursora w trybie przeglądania PDF (R07)."""
		if info is None:
			try:
				info = cm_obj.makeTextInfo(textInfos.POSITION_CARET)
			except Exception:
				return
		self._announce_level_for_info(cm_obj, info)

	def event_caret(self, obj, nextHandler):
		nextHandler()
		conf = config.conf.get(CONFIG_SECTION, {})
		if not conf.get("autoAnnounceLevel", True) or not self._is_target_application_active():
			return

		try:
			ti = getattr(obj, "treeInterceptor", None)
			target_provider = ti if (ti is not None and hasattr(ti, "makeTextInfo")) else obj
			info = target_provider.makeTextInfo(textInfos.POSITION_CARET)
			self._announce_level_for_info(obj, info)
		except Exception:
			pass
