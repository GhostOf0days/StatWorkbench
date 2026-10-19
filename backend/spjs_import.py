"""Translate legacy .spjs JSON workbook files into the built-in workbook model.

The JSON layout is observed in user-created native project files. The public
SpreadJS alignment/border enums are mapped to the installed Univer schema.
Unknown metadata is retained as inert provenance, never executed as code.
"""
from __future__ import annotations

import json
import copy
import math
import re
import uuid
import base64
import binascii

from backend.common import MAX_ROWS, MAX_COLUMNS, MAX_CELLS, MAX_FILE_BYTES, MAX_CELL_CHARACTERS, MAX_TEXT_CHARACTERS

# SpreadJS 9 project values agree with the documented enum values:
# https://developer.mescius.com/spreadjs/api/v16/enums/GC.Spread.Sheets.LineStyle
_BORDER = {0: 0, 1: 1, 2: 8, 3: 4, 4: 3, 5: 13, 6: 7, 7: 2, 8: 9, 9: 5, 10: 10, 11: 6, 12: 11, 13: 12}
_FONT = re.compile(r"^((?:(?:italic|normal|bold|[1-9]00)\s+)*)(\d+(?:\.\d+)?)(px|pt)\s+(.+)$", re.I)
_COLOR = re.compile(r"^(?:#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})|[a-zA-Z]{1,30}|rgba?\([\d.,%\s]+\))$")
_REFERENCE = re.compile(r"\$?([A-Za-z]{1,3})\$?([1-9]\d*)$")
_TOKEN = re.compile(r'''\s*(?:((?:'(?:[^']|'')+'|(?:\[[^\]\r\n]+\])?[A-Za-z_][A-Za-z_0-9 .]*)!)?(\$?[A-Za-z]{1,3}\$?[1-9]\d*)(?![A-Za-z0-9_.]|\s*\()|("(?:[^"]|"")*"|\{(?:[^{}"]|"(?:[^"]|"")*")*\}|\#(?:REF!|DIV/0!|VALUE!|NAME\?|NUM!|N/A|NULL!))|((?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?)|((?:(?:'(?:[^']|'')+'|(?:\[[^\]\r\n]+\])?[A-Za-z_][A-Za-z_0-9 .]*)!)?[A-Za-z_][A-Za-z_0-9.]*)|(<=|>=|<>|[+\-*/^&%=<>() ,:]))''', re.I)
# Native SpreadJS 9 registered names intersected with Univer's actual implemented
# function registry (not its larger documentation list). Only generic function
# names are shared; no original implementations are included. Network/custom
# functions are absent; unavailable functions remain explicit import errors.
_FUNCTIONS = set("""
ABS ACCRINT ACCRINTM ACOS ACOSH ADDRESS AMORLINC AND ASIN ASINH ATAN ATAN2 ATANH AVEDEV AVERAGE AVERAGEA
AVERAGEIF AVERAGEIFS BESSELI BESSELJ BESSELK BESSELY BETA.DIST BETA.INV BETADIST BETAINV BIN2DEC BIN2HEX
BIN2OCT BINOM.DIST BINOM.INV BINOMDIST CEILING CEILING.PRECISE CHAR CHIDIST CHIINV CHISQ.DIST CHISQ.DIST.RT
CHISQ.INV CHISQ.INV.RT CHISQ.TEST CHITEST CHOOSE CLEAN CODE COLUMN COLUMNS COMBIN COMPLEX CONCATENATE
CONFIDENCE CONFIDENCE.NORM CONFIDENCE.T CONVERT CORREL COS COSH COUNT COUNTA COUNTBLANK COUNTIF COUNTIFS
COUPDAYBS COUPDAYS COUPDAYSNC COUPNCD COUPNUM COUPPCD COVAR COVARIANCE.P COVARIANCE.S CRITBINOM CUMIPMT
CUMPRINC DATE DATEDIF DATEVALUE DAVERAGE DAY DAYS360 DB DCOUNT DCOUNTA DDB DEC2BIN DEC2HEX DEC2OCT DEGREES
DELTA DEVSQ DGET DISC DMAX DMIN DOLLAR DOLLARDE DOLLARFR DPRODUCT DSTDEV DSTDEVP DSUM DURATION DVAR DVARP
EDATE EFFECT EOMONTH ERF ERF.PRECISE ERFC ERFC.PRECISE ERROR.TYPE EVEN EXACT EXP EXPON.DIST EXPONDIST F.DIST
F.DIST.RT F.INV F.INV.RT F.TEST FACT FACTDOUBLE FALSE FDIST FIND FINV FISHER FISHERINV FIXED FLOOR
FLOOR.PRECISE FORECAST FREQUENCY FTEST FV FVSCHEDULE GAMMA.DIST GAMMA.INV GAMMADIST GAMMAINV GAMMALN
GAMMALN.PRECISE GCD GEOMEAN GESTEP GROWTH HARMEAN HEX2BIN HEX2DEC HEX2OCT HLOOKUP HOUR HYPGEOM.DIST
HYPGEOMDIST IF IFERROR IMABS IMAGINARY IMARGUMENT IMCONJUGATE IMCOS IMDIV IMEXP IMLN IMLOG10 IMLOG2 IMPOWER
IMPRODUCT IMREAL IMSIN IMSQRT IMSUB IMSUM INDEX INDIRECT INT INTERCEPT INTRATE IPMT IRR ISBLANK ISERR ISERROR
ISEVEN ISLOGICAL ISNA ISNONTEXT ISNUMBER ISODD ISPMT ISREF ISTEXT KURT LARGE LCM LEFT LEN LINEST LN LOG LOG10
LOGEST LOGINV LOGNORM.DIST LOGNORM.INV LOGNORMDIST LOOKUP LOWER MATCH MAX MAXA MDETERM MDURATION MEDIAN MID
MIN MINA MINUTE MINVERSE MIRR MMULT MOD MODE MODE.MULT MODE.SNGL MONTH MROUND MULTINOMIAL N NA NEGBINOM.DIST
NEGBINOMDIST NETWORKDAYS NETWORKDAYS.INTL NOMINAL NORM.DIST NORM.INV NORM.S.DIST NORM.S.INV NORMDIST NORMINV
NORMSDIST NORMSINV NOT NOW NPER NPV OCT2BIN OCT2DEC OCT2HEX ODD ODDFPRICE ODDFYIELD ODDLPRICE ODDLYIELD OFFSET
OR PEARSON PERCENTILE PERCENTILE.EXC PERCENTILE.INC PERCENTRANK PERCENTRANK.EXC PERCENTRANK.INC PERMUT PI PMT
POISSON POISSON.DIST POWER PPMT PRICE PRICEDISC PRICEMAT PROB PRODUCT PROPER PV QUARTILE QUARTILE.EXC
QUARTILE.INC QUOTIENT RADIANS RAND RANDBETWEEN RANK RANK.AVG RANK.EQ RATE RECEIVED REPLACE REPT RIGHT ROMAN
ROUND ROUNDDOWN ROUNDUP ROW ROWS RSQ SEARCH SECOND SERIESSUM SIGN SIN SINH SKEW SLN SLOPE SMALL SQRT SQRTPI
STANDARDIZE STDEV STDEV.P STDEV.S STDEVA STDEVP STDEVPA STEYX SUBSTITUTE SUBTOTAL SUM SUMIF SUMIFS SUMPRODUCT
SUMSQ SUMX2MY2 SUMX2PY2 SUMXMY2 SYD T T.DIST T.DIST.2T T.DIST.RT T.INV T.INV.2T T.TEST TAN TANH TBILLEQ
TBILLPRICE TBILLYIELD TDIST TEXT TIME TIMEVALUE TINV TODAY TRANSPOSE TREND TRIM TRIMMEAN TRUE TRUNC TTEST TYPE
UPPER VALUE VAR VAR.P VAR.S VARA VARP VARPA VDB VLOOKUP WEEKDAY WEEKNUM WEIBULL WEIBULL.DIST WORKDAY
WORKDAY.INTL XIRR XNPV YEAR YEARFRAC YIELD YIELDDISC YIELDMAT Z.TEST ZTEST
""".split())
_ARRAY_VOLATILE_FUNCTIONS = {"RAND", "RANDBETWEEN", "NOW", "TODAY"}
_FUNCTIONS.update({"ISO.CEILING", "EURO", "EUROCONVERT", "AMORDEGRC"})
_FUNCTIONS.add("SWB.CSE")  # Independent single-evaluation legacy-array wrapper.


def _constant_array_valid(text):
    """Validate rectangular literal arrays without evaluating their contents."""
    values = re.findall(r'"(?:[^"]|"")*"|[,;]|[^,;]+', text[1:-1])
    expect_value, width, widths = True, 0, []
    for value in values:
        value = value.strip()
        if expect_value:
            if not re.fullmatch(r'"(?:[^"]|"")*"|TRUE|FALSE|[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[Ee][+-]?\d+)?|\#(?:REF!|DIV/0!|VALUE!|NAME\?|NUM!|N/A|NULL!)', value, re.I):
                return False
            width += 1
        elif value == ';':
            widths.append(width)
            width = 0
        elif value != ',':
            return False
        expect_value = not expect_value
    widths.append(width)
    return not expect_value and bool(width) and len(set(widths)) == 1


def _integer(value, label, minimum=0, maximum=MAX_ROWS):
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"Invalid .spjs {label}; supported limits are {minimum} to {maximum}.")
    return value


def _index(value, label, maximum):
    if not isinstance(value, str) or not re.fullmatch(r"0|[1-9]\d*", value):
        raise ValueError(f"Invalid .spjs {label} index.")
    return _integer(int(value), label, maximum=maximum - 1)


def _color(value):
    return value if isinstance(value, str) and _COLOR.fullmatch(value) else None


def _formula(text, names, definitions=None, trail=(), budget=None, position=None):
    """Validate supported A1 formulas; do not evaluate them in Python."""
    if not isinstance(text, str) or not text.strip() or len(text) > 8192:
        return None
    expression = text.strip().removeprefix("=").strip()
    budget = [0] if budget is None else budget
    consumer = position
    cursor, tokens = 0, []
    while cursor < len(expression):
        budget[0] += 1
        if budget[0] > 16384:
            return None
        match = _TOKEN.match(expression, cursor)
        if not match or len(tokens) >= 2048:
            return None
        sheet, reference, string, number, word, operator = match.groups()
        if reference:
            if sheet:
                name = sheet[:-1]
                if name.startswith("'"):
                    name = name[1:-1].replace("''", "'")
                if '[' in name or ']' in name:
                    # The inspected native resolver cannot open another workbook;
                    # it returns #REF!, and the native save normalizes that error.
                    tokens.append(("value", "#REF!"))
                    cursor = match.end()
                    continue
                if name.casefold() not in names:
                    return None
            ref = _REFERENCE.fullmatch(reference)
            column = 0
            for char in ref[1].upper():
                column = column * 26 + ord(char) - 64
            if column > MAX_COLUMNS or int(ref[2]) > MAX_ROWS:
                return None
            tokens.append(("value", (sheet or "") + reference))
        elif word:
            upper = word.upper()
            following = expression[match.end():].lstrip()
            if '!' in word and not following.startswith('('):
                qualifier, qualified_name = word.rsplit('!', 1)
                qualifier = qualifier[1:-1].replace("''", "'") if qualifier.startswith("'") else qualifier
                if '[' in qualifier or ']' in qualifier:
                    tokens.append(('value', '#REF!'))
                else:
                    scopes = definitions.get('__SCOPES__', {}) if definitions else {}
                    scope = scopes.get(qualifier.casefold())
                    identity = qualifier.casefold() + '!' + qualified_name.upper()
                    if not scope or identity in trail or len(trail) >= 16:
                        return None
                    expanded = _formula(qualified_name, names, scope, (*trail, identity), budget, consumer)
                    if not expanded:return None
                    tokens.append(('value', '(' + expanded[1:] + ')'))
            elif upper in {"TRUE", "FALSE"} and not following.startswith("("):
                tokens.append(("value", upper))
            elif upper in _FUNCTIONS and following.startswith("("):
                tokens.append(("function", upper))
            elif not following.startswith("(") and definitions and upper in definitions and upper not in trail and len(trail) < 16:
                definition = definitions[upper]
                named_text = _name_at(definition, consumer) if isinstance(definition, dict) else definition
                expanded = _formula(named_text, names, definitions, (*trail, upper), budget, consumer)
                if not expanded:
                    return None
                tokens.append(("value", "(" + expanded[1:] + ")"))
            else:
                return None
        elif string or number:
            if string and string.startswith('{') and not _constant_array_valid(string):
                return None
            tokens.append(("value", string or number))
        elif operator != " ":
            tokens.append(("operator", operator))
        cursor = match.end()
    # Basic operand/group balance avoids feeding malformed or implicit-name
    # expressions to the calculation engine. It is not a second evaluator.
    expect_value, stack, previous = True, [], None
    for kind, value in tokens:
        if kind in {"value", "function"}:
            if not expect_value:
                return None
            expect_value = kind == "function"
        elif value == "(":
            if not expect_value:
                return None
            stack.append(previous == "function")
            expect_value = True
        elif value == ")":
            if not stack or (expect_value and not (previous in {"(", ","} and stack[-1])):
                return None
            stack.pop()
            expect_value = False
        elif value == ",":
            if not stack or not stack[-1] or expect_value and previous not in {"(", ","}:
                return None
            expect_value = True
        elif value == "%":
            if expect_value:
                return None
        elif value in {"+", "-"} and expect_value:
            pass
        else:
            if expect_value:
                return None
            expect_value = True
        previous = kind if kind == "function" else value
    if not tokens or expect_value or stack:
        return None
    result = "=" + "".join(token[1] for token in tokens)
    return result if len(result) <= 8192 else None


def _defined_names(source, sheet, sheet_name):
    """Prepare scoped names and retain their native parsing base.

    SpreadJS 9 serializes NameInfo as {name, formula, row, col} in `names`.
    Relative references are shifted at each consumer, preserving mixed $ flags.
    """
    result = {}
    for scope in (source, sheet):
        items = scope.get("names", [])
        if not isinstance(items, list) or len(items) > 10000:
            raise ValueError("Invalid .spjs defined names.")
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("name"), str) or not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9.]*", item["name"]):
                continue
            text = item.get("formula")
            if not isinstance(text, str) or len(text) > 8192:
                continue
            # Skip strings while qualifying references; a name must not change
            # with its consumer's location unless relative-base semantics exist.
            position, parts, valid, relative = 0, [], True, False
            expression = text.strip().removeprefix("=").strip()
            while position < len(expression):
                match = _TOKEN.match(expression, position)
                if not match:
                    valid = False
                    break
                qualifier, reference, string, number, word, operator = match.groups()
                if reference:
                    relative |= not bool(re.fullmatch(r"\$[A-Za-z]{1,3}\$[1-9]\d*", reference))
                    qualifier = qualifier or ("" if parts and parts[-1] == ":" else "'" + sheet_name.replace("'", "''") + "'!")
                    parts.append(qualifier + reference)
                else:
                    parts.append(string or number or word or operator)
                position = match.end()
            # A local invalid definition shadows a valid global one as well.
            row, col = item.get('row'), item.get('col')
            if relative and (isinstance(row, bool) or not isinstance(row, int) or not 0 <= row < MAX_ROWS or isinstance(col, bool) or not isinstance(col, int) or not 0 <= col < MAX_COLUMNS):
                valid = False
            result[item["name"].upper()] = {"formula": "".join(parts), "row": row, "col": col} if valid and relative else "".join(parts) if valid else ""
    return result


def _name_at(definition, consumer):
    if consumer is None:return None
    expression, cursor, parts = definition['formula'], 0, []
    while cursor < len(expression):
        match = _TOKEN.match(expression, cursor)
        if not match:return None
        sheet, reference, string, number, word, operator = match.groups()
        if reference:
            row, col = _reference_parts(reference)
            flags = re.fullmatch(r'(\$?)[A-Za-z]{1,3}(\$?)[1-9]\d*', reference)
            if not flags[1]:col += consumer[1] - definition['col']
            if not flags[2]:row += consumer[0] - definition['row']
            if not 0 <= row < MAX_ROWS or not 0 <= col < MAX_COLUMNS:return None
            absolute = _a1(row, col)
            letters = re.match(r'\$([A-Z]+)', absolute)[1]
            parts.append((sheet or '') + flags[1] + letters + flags[2] + str(row + 1))
        else:parts.append(string or number or word or operator)
        cursor = match.end()
    return ''.join(parts)


def _reference_parts(reference):
    match = _REFERENCE.fullmatch(reference)
    column = 0
    for char in match[1].upper():
        column = column * 26 + ord(char) - 64
    return int(match[2]) - 1, column - 1


def _a1(row, column):
    letters = ""
    column += 1
    while column:
        column, remainder = divmod(column - 1, 26)
        letters = chr(65 + remainder) + letters
    return f"${letters}${row + 1}"


def _array_element(expression, offset_row, offset_col, height, width):
    """Scalarize a bounded elementwise legacy array without cached results.

    Reducers/matrix functions are deliberately excluded: scalarizing SUM over
    an array would change its meaning. One-row/one-column operands broadcast.
    """
    if not expression:
        return None
    text, position, parts = expression[1:], 0, []
    elementwise = set("ABS SQRT ROUND ROUNDUP ROUNDDOWN INT MOD POWER EXP LN LOG LOG10 IF IFERROR NOT NA".split())
    while position < len(text):
        match = _TOKEN.match(text, position)
        if not match:
            return None
        sheet, reference, string, number, word, operator = match.groups()
        position = match.end()
        if reference:
            end = re.match(r"\s*:\s*(\$?[A-Za-z]{1,3}\$?[1-9]\d*)", text[position:])
            if end:
                r, c = _reference_parts(reference)
                er, ec = _reference_parts(end[1])
                h, w = er - r + 1, ec - c + 1
                if h not in {1, height} or w not in {1, width}:
                    return None
                parts.append((sheet or "") + _a1(r + (offset_row if h > 1 else 0), c + (offset_col if w > 1 else 0)))
                position += end.end()
            else:
                parts.append((sheet or "") + reference)
        elif word:
            if text[position:].startswith("(") and word.upper() not in elementwise:
                return None
            parts.append(word)
        elif operator == ":" or string and string.startswith('{'):
            return None
        else:
            parts.append(string or number or operator)
    return "=" + "".join(parts)


def _array_projection(expression, row, column):
    """Select one live result, preserving native singleton broadcast and padding.

    INDEX evaluates its array argument in the spreadsheet engine. ROWS/COLUMNS
    retain shape changes after source edits; excess output cells become #N/A.
    Volatile and external-I/O functions are outside the accepted vocabulary.
    """
    if not expression:
        return None
    body = expression[1:]
    # Projection can evaluate its argument more than once. Repeating a volatile
    # array expression would silently change its result, so retain it as an
    # explicit unsupported group instead. Ordinary scalar uses remain live.
    if any(match[5] and match[5].upper() in _ARRAY_VOLATILE_FUNCTIONS and body[match.end():].lstrip().startswith('(') for match in _TOKEN.finditer(body)):
        return None
    r = f'IF(ROWS({body})=1,1,{row + 1})' if row else '1'
    c = f'IF(COLUMNS({body})=1,1,{column + 1})' if column else '1'
    selected = f'INDEX({body},{r},{c})'
    guards = []
    if row:guards.append(f'AND(ROWS({body})<>1,ROWS({body})<{row + 1})')
    if column:guards.append(f'AND(COLUMNS({body})<>1,COLUMNS({body})<{column + 1})')
    result = '=' + (f'IF(OR({",".join(guards)}),NA(),{selected})' if guards else selected)
    return result if len(result) <= 8192 else None


def _array_anchor_context(expression, row, column):
    if expression is None:return None
    text, cursor, result = expression[1:], 0, []
    while cursor < len(text):
        token = _TOKEN.match(text, cursor)
        if not token:return None
        qualifier, reference, string, number, word, operator = token.groups()
        following = text[token.end():]
        if word and word.upper() in {'ROW', 'COLUMN'} and following.startswith('()'):
            result.append(word.upper() + '(' + _a1(row, column) + ')')
            cursor = token.end() + 2
        else:
            result.append((qualifier or '') + reference if reference else string or number or word or operator)
            cursor = token.end()
    return '=' + ''.join(result)


def _expand_arrays(table, sheet_names, definitions, notes, sheet_name, generated_budget=None):
    arrays = []
    for row, cells in table.items():
        if not isinstance(cells, dict):
            continue
        for column, cell in cells.items():
            if isinstance(cell, dict) and "arrayInfo" in cell:
                info = cell["arrayInfo"]
                if not isinstance(info, dict):
                    raise ValueError("Invalid .spjs array formula range.")
                r = _integer(info.get("row"), "array row", maximum=MAX_ROWS - 1)
                c = _integer(info.get("col"), "array column", maximum=MAX_COLUMNS - 1)
                h = _integer(info.get("rowCount"), "array height", 1, MAX_ROWS - r)
                w = _integer(info.get("colCount"), "array width", 1, MAX_COLUMNS - c)
                if str(r) != row or str(c) != column or h * w > MAX_CELLS:
                    raise ValueError("Invalid .spjs array formula anchor or size.")
                arrays.append((r, c, h, w, cell.get("formula")))
    if not arrays:
        return table
    if sum(h * w for r, c, h, w, f in arrays) > MAX_CELLS:
        raise ValueError("The .spjs array formulas exceed the cell limit.")
    # Charge the generated formula, its saved provenance and per-cell metadata
    # before expanding compact native arrayInfo records. The budget is shared
    # across sheets, preventing a small file from allocating gigabytes of cells.
    generated_budget = [0] if generated_budget is None else generated_budget
    plans = []
    for r, c, h, w, original in arrays:
        expression = _array_anchor_context(_formula(original, sheet_names, definitions, position=(r, c)), r, c)
        single = bool(expression and any(match[5] and match[5].upper() in _ARRAY_VOLATILE_FUNCTIONS and expression[1:][match.end():].lstrip().startswith('(') for match in _TOKEN.finditer(expression[1:])))
        projector = _array_element if _array_element(expression, 0, 0, h, w) is not None else lambda expr, dr, dc, height, width: _array_projection(expr, dr, dc)
        largest = f'=SWB.CSE({expression[1:]},{h},{w})' if single else projector(expression, h - 1, w - 1, h, w)
        supported = largest is not None
        metadata = {"formula": original, "row": r, "col": c, "rowCount": h, "colCount": w, "supported": supported}
        if single:metadata['singleEvaluation'] = True
        per_cell = 2 * len((largest or 'UNSUPPORTED_ARRAY()').encode('utf-8')) + len(json.dumps(metadata, ensure_ascii=False).encode('utf-8')) + 160
        generated_budget[0] += h * w * per_cell
        if generated_budget[0] > 2 * MAX_TEXT_CHARACTERS:
            raise ValueError('The .spjs array formulas exceed the 32 MB expanded formula and metadata limit; split the array ranges or workbook.')
        plans.append((r, c, h, w, expression, projector, supported, metadata))
    result, occupied = copy.deepcopy(table), set()
    for r, c, h, w, expression, projector, supported, metadata in plans:
        for dr in range(h):
            for dc in range(w):
                location = (r + dr, c + dc)
                if location in occupied:
                    raise ValueError("The .spjs array formula ranges overlap.")
                occupied.add(location)
                cell = result.setdefault(str(r + dr), {}).setdefault(str(c + dc), {})
                if not isinstance(cell, dict):
                    raise ValueError("Invalid .spjs array formula cell.")
                cell.pop("arrayInfo", None)
                cell["statworkbenchArray"] = metadata
                if metadata.get('singleEvaluation'):
                    cell['value'] = None
                    cell.pop('formula', None)
                    if dr == 0 and dc == 0:cell['formula'] = f'=SWB.CSE({expression[1:]},{h},{w})'
                else:
                    cell["formula"] = projector(expression, dr, dc, h, w) if supported else "UNSUPPORTED_ARRAY()"
        notes.append(f"{sheet_name} R{r + 1}C{c + 1}: {h}×{w} array formula " + ("restored as live formulas." if supported else "uses unsupported array semantics; the entire result range displays #N/A."))
    return result


def _style(value, named, seen=()):
    if isinstance(value, str):
        if value in seen or value not in named:
            return {}
        return _style(named[value], named, (*seen, value))
    if not isinstance(value, dict):
        return {}
    result = _style(value.get("parentName"), named, seen)
    if isinstance(value.get("hAlign"), int) and value["hAlign"] in {0, 1, 2, 3, 5, 6}:
        result["ht"] = {0: 1, 1: 2, 2: 3, 3: 0, 5: 6, 6: 4}[value["hAlign"]]
    if isinstance(value.get("vAlign"), int) and value["vAlign"] in {0, 1, 2}:
        result["vt"] = value["vAlign"] + 1
    font = _FONT.fullmatch(value.get("font", "")) if isinstance(value.get("font", ""), str) else None
    if font:
        flags, size, units, family = font.groups()
        size = float(size) * (0.75 if units.lower() == "px" else 1)
        if 1 <= size <= 200:
            result.update(fs=round(size, 5), ff=family.strip("\"'"), bl=int(bool(re.search(r"bold|[6-9]00", flags, re.I))), it=int("italic" in flags.lower()))
    if isinstance(value.get("formatter"), str) and len(value["formatter"]) <= 1024:
        result["n"] = {"pattern": value["formatter"]}
    for original, translated in (("backColor", "bg"), ("foreColor", "cl")):
        if color := _color(value.get(original)):
            result[translated] = {"rgb": color}
    if isinstance(value.get("wordWrap"), bool):
        result["tb"] = 3 if value["wordWrap"] else 1
    borders = {}
    for name, key in (("borderBottom", "b"), ("borderTop", "t"), ("borderLeft", "l"), ("borderRight", "r")):
        border = value.get(name)
        if isinstance(border, dict) and isinstance(border.get("style"), int) and border["style"] in _BORDER:
            borders[key] = {"s": _BORDER[border["style"]], "cl": {"rgb": _color(border.get("color")) or "#000000"}}
    if borders:
        result["bd"] = {**result.get("bd", {}), **borders}
    return result


def _axes(items, limit, dimension, named):
    if items is None:
        return {}
    if isinstance(items, list):
        if len(items) > limit:
            raise ValueError("The .spjs row/column metadata exceeds supported limits.")
        iterator = enumerate(items)
    elif isinstance(items, dict):
        iterator = ((_index(key, "axis", limit), value) for key, value in items.items())
    else:
        raise ValueError("Unsupported .spjs row/column metadata.")
    result = {}
    for index, item in iterator:
        if item is None:
            continue
        if not isinstance(item, dict):
            raise ValueError("Invalid .spjs row/column settings.")
        translated = {}
        size = item.get("size")
        if isinstance(size, (int, float)) and not isinstance(size, bool) and math.isfinite(size) and 0 <= size <= 2000:
            translated[dimension] = size
        if item.get("visible") is False or size == 0:
            translated["hd"] = 1
        if style := _style(item.get("style"), named):
            translated["s"] = style
        if translated:
            result[str(index)] = translated
    return result


def _embedded_image(source):
    """Accept bounded embedded raster bytes; never fetch an image URL."""
    if not isinstance(source, str):
        return False
    match = re.fullmatch(r'data:image/(png|jpeg|gif|webp|bmp);base64,([A-Za-z0-9+/=\r\n]+)', source, re.I)
    if not match or len(match[2]) > 23 * 1024 * 1024:
        return False
    try:
        raw = base64.b64decode(match[2].replace('\n', '').replace('\r', ''), validate=True)
    except (ValueError, binascii.Error):
        return False
    if not 1 <= len(raw) <= 16 * 1024 * 1024:
        return False
    signatures = {'png': raw.startswith(b'\x89PNG\r\n\x1a\n'), 'jpeg': raw.startswith(b'\xff\xd8\xff'), 'gif': raw.startswith((b'GIF87a', b'GIF89a')), 'webp': raw.startswith(b'RIFF') and raw[8:12] == b'WEBP', 'bmp': raw.startswith(b'BM')}
    return signatures[match[1].lower()]


def _image_position(picture):
    position = {key: picture.get(original, 0 if key in {'left', 'top'} else None) for key, original in [('left', 'x'), ('top', 'y'), ('width', 'width'), ('height', 'height')]}
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in position.values()):
        return None
    if not 0 <= position['left'] <= MAX_COLUMNS * 2000 or not 0 <= position['top'] <= MAX_ROWS * 2000:
        return None
    if not 1 <= position['width'] <= 20000 or not 1 <= position['height'] <= 20000 or position['width'] * position['height'] > 36000000:
        return None
    return position


def _images(sheet_id, original, notes):
    objects = original.get('floatingObjects', [])
    if not isinstance(objects, list) or len(objects) > 1000:
        raise ValueError('Invalid .spjs drawing list; at most 1,000 drawings per sheet are supported.')
    result = []
    for index, picture in enumerate(objects):
        if not isinstance(picture, dict) or picture.get('floatingObjectType') != 1:
            notes.append(f'{original.get("name", "Worksheet")} drawing {index + 1}: unknown or HTML drawing retained as inert metadata.')
            continue
        position = _image_position(picture)
        if not position or not _embedded_image(picture.get('src')):
            notes.append(f'{original.get("name", "Worksheet")} drawing {index + 1}: unavailable embedded raster data or unsupported geometry; original metadata retained without fetching external resources.')
            continue
        result.append({'sheetId': sheet_id, 'originalIndex': index, 'source': picture['src'], 'position': position, 'native': copy.deepcopy(picture)})
    return result


def _export_images(native, sheet_id, registry, warnings):
    managed = native.pop('managedImageIndices', [])
    if registry is None:
        return
    objects = native.get('floatingObjects', [])
    if not isinstance(objects, list) or not isinstance(managed, list) or any(isinstance(i, bool) or not isinstance(i, int) or not 0 <= i < len(objects) for i in managed):
        raise ValueError('Invalid original-project image metadata.')
    selected = [entry for entry in registry if entry.get('sheetId') == sheet_id]
    registered = set()
    converted = []
    for number, entry in enumerate(selected):
        index = entry.get('originalIndex')
        if index is not None:
            if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(objects) or index in registered:
                raise ValueError('Invalid or duplicate original picture index.')
            registered.add(index)
        picture = copy.deepcopy(objects[index]) if index is not None else copy.deepcopy(entry.get('native', {}))
        if not isinstance(picture, dict):
            raise ValueError('Invalid worksheet image metadata.')
        current = entry.get('native', {})
        if not isinstance(current, dict):
            raise ValueError('Invalid worksheet image metadata.')
        for key in ('dynamicMove', 'dynamicSize', 'fixedPosition', 'canPrint', 'isLocked', 'isVisible', 'allowMove', 'allowResize'):
            if key in current:
                if not isinstance(current[key], bool):raise ValueError('Invalid worksheet picture placement option.')
                picture[key] = current[key]
        for key in ('backColor', 'borderColor'):
            if key in current:
                if current[key] is not None and not _color(current[key]):raise ValueError('Invalid worksheet picture color.')
                picture[key] = current[key]
        if 'pictureStretch' in current:
            if isinstance(current['pictureStretch'], bool) or current['pictureStretch'] not in (0, 1, 2, 3):raise ValueError('Invalid worksheet picture fit mode.')
            picture['pictureStretch'] = current['pictureStretch']
        for key, low in (('borderRadius', -1), ('borderWidth', 0)):
            if key in current:
                value = current[key]
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= 20000:raise ValueError('Invalid worksheet picture border.')
                picture[key] = value
        if 'borderStyle' in current:
            if current['borderStyle'] not in ('none', 'hidden', 'solid', 'dashed', 'dotted', 'double', 'groove', 'ridge', 'inset', 'outset'):raise ValueError('Invalid worksheet picture border style.')
            picture['borderStyle'] = current['borderStyle']
        if entry.get('flattenedStyle') is True:
            warnings.append('A resized styled picture was exported with its displayed appearance embedded in the image.')
        position = entry.get('position', {})
        if not isinstance(position, dict):
            raise ValueError('Invalid worksheet image placement.')
        picture.update(floatingObjectType=1, src=entry.get('source'), x=position.get('left'), y=position.get('top'), width=position.get('width'), height=position.get('height'))
        picture.setdefault('name', f'StatWorkbenchPicture{number + 1}')
        if not _embedded_image(picture['src']) or not _image_position(picture):
            raise ValueError('A worksheet picture needs bounded embedded raster data and valid placement.')
        converted.append(picture)
    retained = [copy.deepcopy(picture) for index, picture in enumerate(objects) if index not in managed and index not in registered]
    names = {picture.get('name') for picture in retained if isinstance(picture, dict) and isinstance(picture.get('name'), str)}
    for picture in converted:
        base = str(picture.get('name') or 'StatWorkbenchPicture')[:200]
        name, suffix = base, 2
        while name in names:
            name = f'{base} ({suffix})';suffix += 1
        picture['name'] = name;names.add(name)
    if retained or converted:
        native['floatingObjects'] = [*retained, *converted]
    else:
        native.pop('floatingObjects', None)


def _restore_array_groups(cells, table, warnings=None):
    """Restore native CSE groups only while every translated result is intact."""
    candidates = {}
    for row in cells.values():
        for cell in row.values():
            if not isinstance(cell, dict):continue
            prior = cell.get('custom', {}).get('statplusImport', {})
            info = prior.get('metadata', {}).get('statworkbenchArray') if isinstance(prior, dict) else None
            if isinstance(info, dict) and info.get('supported') is True:
                r = _integer(info.get('row'), 'array row', maximum=MAX_ROWS - 1)
                c = _integer(info.get('col'), 'array column', maximum=MAX_COLUMNS - 1)
                h = _integer(info.get('rowCount'), 'array height', 1, MAX_ROWS - r)
                w = _integer(info.get('colCount'), 'array width', 1, MAX_COLUMNS - c)
                if h * w > MAX_CELLS:raise ValueError('The .spjs array formula exceeds the cell limit.')
                candidates[(r, c)] = info
    visited = 0
    for (r, c), info in candidates.items():
        h, w = info['rowCount'], info['colCount']
        visited += h * w
        if visited > MAX_CELLS:raise ValueError('The .spjs array formulas exceed the cell limit.')
        intact = True
        for dr in range(h):
            for dc in range(w):
                cell = cells.get(str(r + dr), {}).get(str(c + dc), {})
                prior = cell.get('custom', {}).get('statplusImport', {}) if isinstance(cell, dict) else {}
                saved = prior.get('metadata', {}).get('statworkbenchArray')
                expected = prior.get('translatedFormula', '=' + str(prior.get('formula', '')).removeprefix('='))
                member = info.get('singleEvaluation') and (dr != 0 or dc != 0)
                if member:expected = None
                if saved != info or cell.get('f') != expected or member and cell.get('v') is not None:
                    intact = False
                    break
            if not intact:break
        if not intact:
            anchor = table.get(str(r), {}).get(str(c), {})
            if info.get('singleEvaluation') and str(anchor.get('formula', '')).startswith('SWB.CSE('):
                anchor['statworkbenchOriginalFormula'] = anchor['formula']
                anchor['formula'] = 'NA()'
                if warnings is not None:warnings.append('A modified volatile array cannot be restored as a native group without overwriting its edited cells; its anchor exports as #N/A and the original expression is retained as metadata.')
            continue
        for dr in range(h):
            for dc in range(w):
                target = table.setdefault(str(r + dr), {}).setdefault(str(c + dc), {})
                target.pop('formula', None)
        table[str(r)][str(c)].update(formula=info['formula'].removeprefix('='), arrayInfo={key: info[key] for key in ('row', 'col', 'rowCount', 'colCount')})


def _charts(raw, index_ids, translated_sheets, notes):
    if not isinstance(raw, list) or len(raw) > 1000:
        raise ValueError("Invalid .spjs chart list; at most 1,000 charts are supported.")
    translated, point_count = [], 0
    for index, original in enumerate(raw):
        if not isinstance(original, dict) or not isinstance(original.get("options"), dict):
            notes.append(f"Chart {index + 1} has an unknown structure; its original metadata is retained.")
            continue
        options = original["options"]
        sheet_id = index_ids.get(original.get("sheetIndex"))
        series = options.get("series")
        valid = sheet_id and isinstance(series, list) and bool(series)
        series_out = []
        if valid:
            for entry in series:
                if not isinstance(entry, dict) or entry.get("type") not in {"line", "spline", "step", "scatter", "bar"} or not isinstance(entry.get("y"), list):
                    valid = False
                    break
                y = entry["y"]
                axis = options.get("axis", {})
                x_axis = axis.get("x", {}) if isinstance(axis, dict) else {}
                categories = x_axis.get("categories") if isinstance(x_axis, dict) else None
                default_x = [i + 0.5 for i in range(len(y))] if isinstance(categories, list) and len(categories) == len(y) else list(range(1, len(y) + 1))
                x = entry.get("x", default_x)
                point_count += len(y)
                if point_count > MAX_CELLS:
                    raise ValueError("The .spjs chart points exceed supported limits.")
                if not y or not isinstance(x, list) or len(x) != len(y) or any(v is not None and (not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v)) for v in y) or any(v is not None and (not isinstance(v, (str, int, float)) or isinstance(v, bool) or (isinstance(v, (int, float)) and not math.isfinite(v))) for v in x):
                    valid = False
                    break
                series_out.append({"name": str(entry.get("label", "Series")), "type": entry["type"], "x": x, "y": y, "color": _color(entry.get("color")) or "#4869df"})
                width = entry.get("width")
                if isinstance(width, (int, float)) and not isinstance(width, bool) and math.isfinite(width) and 0.25 <= width <= 12:
                    series_out[-1]["width"] = width
                markers = entry.get("markers")
                if isinstance(markers, dict):
                    translated_markers = {}
                    if isinstance(markers.get("visible"), bool):
                        translated_markers["visible"] = markers["visible"]
                    radius = markers.get("r")
                    if isinstance(radius, (int, float)) and not isinstance(radius, bool) and math.isfinite(radius) and 1 <= radius <= 20:
                        translated_markers["radius"] = radius
                    if markers.get("style") == "nofill":
                        translated_markers["style"] = "nofill"
                    if translated_markers:
                        series_out[-1]["markers"] = translated_markers
                dash = entry.get("line-style", entry.get("dashStyle"))
                if dash in {"dash", "dot", "dashdot"}:
                    series_out[-1]["dash"] = dash
        kinds = {series["type"] for series in series_out}
        row, column = options.get("row", 0), options.get("col", 0)
        if not isinstance(row, int) or isinstance(row, bool) or not 0 <= row < MAX_ROWS - 100 or not isinstance(column, int) or isinstance(column, bool) or not 0 <= column < (translated_sheets[sheet_id]["columnCount"] if sheet_id else 0):
            valid = False
        if not valid:
            notes.append(f"Chart {index + 1} uses an unsupported chart type, position or series; its original metadata is retained.")
            continue
        chart = {"title": str(options.get("title", "Imported chart")), "type": "bar" if "bar" in kinds else "scatter" if kinds == {"scatter"} else "line", "series": series_out, "legend": options.get("legend") != 0}
        styles = {entry.get("bar-style") for entry in series if entry.get("type") == "bar"}
        if styles == {"stacked"}:chart["stack"] = "normal"
        elif styles == {"percentstack"}:chart["stack"] = "percent"
        for axis in ("X", "Y"):
            if options.get("revertAxis" + axis) is True:chart["reverse" + axis] = True
        axes = options.get("axis", {})
        for axis in ("x", "y"):
            values = axes.get(axis, {}) if isinstance(axes, dict) else {}
            if isinstance(values, dict):
                if axis == "x" and isinstance(values.get("categories"), list) and all(isinstance(label, str) for label in values["categories"]):
                    labels = values["categories"]
                    centers = next((s["x"] for s in series_out if s["type"] == "bar" and len(s["x"]) == len(labels) and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in s["x"])), [i + 0.5 for i in range(len(labels))])
                    chart["xTicks"] = [{"value": centers[index], "label": label} for index, label in enumerate(labels)]
                if isinstance(values.get("label"), str):
                    chart[f"{axis}Label"] = values["label"]
                for original_key, translated_key in (("min", "Min"), ("max", "Max"), ("majorunit", "MajorUnit")):
                    v = values.get(original_key)
                    if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v):
                        chart[f"{axis}{translated_key}"] = v
        position = {"row": row, "column": column}
        # Native projects usually record chart size in occupied grid cells.
        native_sheet = translated_sheets[sheet_id]
        for span_key, size_key, axis_key, item_key, start in (("cwidth", "width", "columnData", "w", column), ("cheight", "height", "rowData", "h", row)):
            span = options.get(span_key)
            if size_key not in options and isinstance(span, int) and not isinstance(span, bool) and 1 <= span <= 100:
                default_size = native_sheet["defaultColumnWidth" if item_key == "w" else "defaultRowHeight"]
                position[size_key] = sum(native_sheet[axis_key].get(str(i), {}).get(item_key, default_size) for i in range(start, start + span))
        for dimension, default, minimum in (("width", 680, 160), ("height", 420, 100)):
            value = options.get(dimension, position.get(dimension, default))
            position[dimension] = value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and minimum <= value <= 2000 else default
        translated.append({"sheetId": sheet_id, "chart": chart, "position": position, "originalIndex": index})
    return translated


def translate_workbook(document, name, selected, scalar):
    """Return a bounded Univer snapshot, charts and an explicit conversion report."""
    source = document["workbook"]
    sheets = source["sheets"]
    if not 1 <= len(sheets) <= 100:
        raise ValueError("The .spjs workbook must contain 1 to 100 worksheets.")
    names = sorted(sheets, key=lambda key: sheets[key].get("index", 0) if isinstance(sheets[key].get("index", 0), int) else 0)
    actual_names = [sheets[key].get("name", key) for key in names]
    if any(not isinstance(value, str) or not value.strip() or len(value) > 31 or re.search(r"[\\/?*\[\]:]", value) for value in actual_names) or len({value.casefold() for value in actual_names}) != len(actual_names):
        raise ValueError("Invalid or duplicate .spjs worksheet names.")
    named_list = source.get("namedStyles", [])
    if not isinstance(named_list, list) or len(named_list) > 10000:
        raise ValueError("Invalid .spjs named styles.")
    named = {style["name"]: style for style in named_list if isinstance(style, dict) and isinstance(style.get("name"), str)}
    notes = ["Original worksheet coordinates, sheet order, report cells, common formatting and merged ranges are restored. No synthetic header row is inserted."]
    snapshot = {"id": "spjs-" + uuid.uuid4().hex, "name": name, "appVersion": "1.0.4", "locale": "enUS", "styles": {}, "sheetOrder": [], "sheets": {}}
    total, text_count, live, unsupported = 0, 0, 0, []
    generated_budget = [0]
    ids, index_ids, images = {}, {}, []
    scopes = {actual_names[number].casefold(): _defined_names(source, sheets[key], actual_names[number]) for number, key in enumerate(names)}
    for definitions in scopes.values():definitions['__SCOPES__'] = scopes
    for number, key in enumerate(names):
        original = sheets[key]
        definitions = scopes[actual_names[number].casefold()]
        sheet_id = "spjs-sheet-" + uuid.uuid4().hex
        ids[key] = sheet_id
        original_index = original.get("index", number)
        if isinstance(original_index, int) and not isinstance(original_index, bool):
            index_ids[original_index] = sheet_id
        data = original.get("data", {})
        table = data.get("dataTable", {}) if isinstance(data, dict) else None
        if not isinstance(table, dict):
            raise ValueError("Unsupported .spjs cell data structure.")
        table = _expand_arrays(table, {value.casefold() for value in actual_names}, definitions, notes, actual_names[number], generated_budget)
        cells, last_row, last_col = {}, -1, -1
        for row_key, row in table.items():
            r = _index(row_key, "row", MAX_ROWS)
            if not isinstance(row, dict):
                raise ValueError("Invalid .spjs cell row.")
            for col_key, cell in row.items():
                if not str(col_key).isdigit():
                    continue
                c = _index(col_key, "column", MAX_COLUMNS)
                if not isinstance(cell, dict):
                    raise ValueError("Invalid .spjs cell.")
                total += 1
                if total > MAX_CELLS:
                    raise ValueError("The .spjs workbook exceeds two million stored cells.")
                last_row, last_col = max(last_row, r), max(last_col, c)
                translated, provenance = {}, {}
                value = cell.get("value")
                if isinstance(value, (dict, list)):
                    provenance["structuredValue"] = value
                    value = value.get("_calcError", value.get("_error")) if isinstance(value, dict) else None
                if value is not None:
                    value = scalar(value)
                    if isinstance(value, str):
                        if len(value) > MAX_CELL_CHARACTERS:
                            raise ValueError("An .spjs cell exceeds the text limit.")
                        text_count += len(value)
                        if text_count > MAX_TEXT_CHARACTERS:
                            raise ValueError("The .spjs workbook exceeds the text limit.")
                    translated.update(v=value, t=3 if isinstance(value, bool) else 2 if isinstance(value, (int, float)) else 1)
                if "formula" in cell:
                    formula = cell["formula"]
                    if not isinstance(formula, str) or len(formula) > MAX_CELL_CHARACTERS:
                        raise ValueError("Invalid .spjs formula text.")
                    converted = _formula(formula, {value.casefold() for value in actual_names}, definitions, position=(r, c))
                    provenance.update(formula=formula, cachedValue=value, formulaStatus="translated" if converted else "unsupported")
                    if converted and converted != "=" + formula.strip().removeprefix("=").strip():
                        provenance["translatedFormula"] = converted
                    # #N/A propagates through dependent formulas; an unsupported
                    # cached result must never appear to be a current calculation.
                    translated.pop("t", None)
                    translated["f"] = converted or "=NA()"
                    translated["v"] = None
                    if converted:
                        live += 1
                    else:
                        unsupported.append({"sheet": actual_names[number], "row": r, "column": c, "formula": formula})
                if style := _style(cell.get("style"), named):
                    translated["s"] = style
                if "style" in cell:
                    provenance["style"] = cell["style"]
                extra = {k: v for k, v in cell.items() if k not in {"value", "style", "formula"}}
                if extra:
                    provenance["metadata"] = extra
                if provenance:
                    translated["custom"] = {"statplusImport": provenance}
                if translated:
                    cells.setdefault(row_key, {})[col_key] = translated
        rows = max(last_row + 1, _integer(original.get("rowCount", 200), "row count", 1, MAX_ROWS))
        columns = max(last_col + 1, _integer(original.get("columnCount", 20), "column count", 1, MAX_COLUMNS))
        spans = original.get("spans", [])
        if not isinstance(spans, list) or len(spans) > 100000:
            raise ValueError("Invalid .spjs merged ranges.")
        merges, merged_rows, merged_cells = [], {}, 0
        for span in spans:
            if not isinstance(span, dict):
                raise ValueError("Invalid .spjs merged range.")
            r = _integer(span.get("row"), "merge row", maximum=rows - 1)
            c = _integer(span.get("col"), "merge column", maximum=columns - 1)
            height = _integer(span.get("rowCount"), "merge height", 1, rows - r)
            width = _integer(span.get("colCount"), "merge width", 1, columns - c)
            merged_cells += height * width
            if merged_cells > MAX_CELLS:
                raise ValueError("The .spjs merged ranges exceed the cell limit.")
            for covered_row in range(r, r + height):
                merged_rows.setdefault(covered_row, []).append((c, c + width - 1))
            merges.append({"startRow": r, "endRow": r + height - 1, "startColumn": c, "endColumn": c + width - 1})
        for intervals in merged_rows.values():
            previous_end = -1
            for start, end in sorted(intervals):
                if start <= previous_end:
                    raise ValueError("The .spjs merged ranges overlap.")
                previous_end = end
        default = data.get("defaultDataNode", {})
        default = _style(default.get("style"), named) if isinstance(default, dict) else {}
        translated = {"id": sheet_id, "name": actual_names[number], "rowCount": rows, "columnCount": columns, "cellData": cells, "mergeData": merges, "columnData": _axes(original.get("columns"), columns, "w", named), "rowData": _axes(original.get("rows"), rows, "h", named), "defaultColumnWidth": 64, "defaultRowHeight": 20, "rowHeader": {"width": 46}, "columnHeader": {"height": 24}, "showGridlines": int(original.get("showGridLine", True) is not False), "zoomRatio": 1, "defaultStyle": default, "custom": {"statplusImport": {k: v for k, v in original.items() if k != "data"}, "statplusDataMetadata": {k: v for k, v in data.items() if k != "dataTable"}}}
        snapshot["sheetOrder"].append(sheet_id)
        snapshot["sheets"][sheet_id] = translated
        sheet_images = _images(sheet_id, original, notes)
        images.extend(sheet_images)
        if len(images) > 1000:
            raise ValueError('The .spjs workbook exceeds the 1,000-picture limit.')
        translated['custom']['statplusImport']['managedImageIndices'] = [item['originalIndex'] for item in sheet_images]
    if live or unsupported:
        notes.append(f"Formulas are never evaluated by the importer. {live} supported A1 formulas recalculate in the spreadsheet; {len(unsupported)} unsupported formulas display #N/A. Original expressions and cached values remain in project metadata.")
    if unsupported:
        notes.append("Unsupported formula locations: " + ", ".join(f"{item['sheet']} R{item['row'] + 1}C{item['column'] + 1}" for item in unsupported[:20]) + (" …" if len(unsupported) > 20 else ""))
    charts = _charts(document.get("charts", []), index_ids, snapshot["sheets"], notes)
    if charts:
        notes.append(f"{len(charts)} line/spline/scatter/bar charts are translated with original data, axes, marker visibility, line widths and placement. Splines use independent Catmull–Rom interpolation; exact native smoothing and styling remain unverified.")
    metadata = {"sourceFormat": "spjs", "version": source.get("version"), "formulaPolicy": "supported-A1-and-scoped-names; unsupported-to-NA", "notes": notes, "unsupportedFormulas": unsupported, "charts": document.get("charts", []), "managedChartIndices": [chart["originalIndex"] for chart in charts], "chartSheetIds": [index_ids.get(chart.get("sheetIndex")) if isinstance(chart, dict) else None for chart in document.get("charts", [])], "workbookMetadata": {k: v for k, v in source.items() if k not in {"sheets"}}, "documentMetadata": {k: v for k, v in document.items() if k not in {"workbook", "charts"}}}
    metadata['importedImages'] = images
    snapshot["custom"] = {"statworkbenchActiveSheetId": ids[selected], "statplusImport": metadata}
    if len(json.dumps(snapshot, ensure_ascii=False, allow_nan=False).encode("utf-8")) > MAX_FILE_BYTES:
        raise ValueError("The converted .spjs workbook exceeds the 64 MiB project limit.")
    return snapshot, charts, notes


def _export_style(style, original=None):
    """Translate common Univer style fields, retaining unknown native fields."""
    result = copy.deepcopy(original) if isinstance(original, dict) else {}
    if not isinstance(style, dict):
        return result
    mappings = {"ht": ("hAlign", {1: 0, 2: 1, 3: 2, 0: 3, 6: 5, 4: 6}), "vt": ("vAlign", {1: 0, 2: 1, 3: 2})}
    for key, (target, mapping) in mappings.items():
        if style.get(key) in mapping:
            result[target] = mapping[style[key]]
    if isinstance(style.get("fs"), (int, float)) and 1 <= style["fs"] <= 200:
        result["font"] = ("italic " if style.get("it") else "") + ("bold " if style.get("bl") else "") + f'{style["fs"]}pt ' + str(style.get("ff", "Arial"))
    if isinstance(style.get("n"), dict) and isinstance(style["n"].get("pattern"), str):
        result["formatter"] = style["n"]["pattern"]
    for key, target in (("bg", "backColor"), ("cl", "foreColor")):
        if isinstance(style.get(key), dict) and (color := _color(style[key].get("rgb"))):
            result[target] = color
    if "tb" in style:
        result["wordWrap"] = style["tb"] == 3
    reverse_border = {value: key for key, value in _BORDER.items()}
    for key, target in (("b", "borderBottom"), ("t", "borderTop"), ("l", "borderLeft"), ("r", "borderRight")):
        value = style.get("bd", {}).get(key) if isinstance(style.get("bd", {}), dict) else None
        if isinstance(value, dict) and value.get("s") in reverse_border:
            result[target] = {"style": reverse_border[value["s"]], "color": _color(value.get("cl", {}).get("rgb")) or "#000000"}
    return result


def _chart_geometry(chart):
    """Express boxes and unequal bins using the native renderer's XY primitives."""
    raw = chart.get('series')
    if not isinstance(raw, list) or not raw or len(raw) > 1000:
        raise ValueError('Invalid worksheet chart series.')
    def finite(value):
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    if chart.get('type') == 'box':
        lines, ticks, extents = [], [], []
        width = min(len(raw) / 12, .45)
        for i, series in enumerate(raw):
            if not isinstance(series, dict) or not isinstance(series.get('y'), list):raise ValueError('Invalid box data.')
            values = sorted(v for v in series['y'] if finite(v))
            if not values:continue
            box = series.get('box', {})
            if not isinstance(box, dict):raise ValueError('Invalid box statistics.')
            def quantile(p):
                index = (len(values) - 1) * p;low = math.floor(index)
                return values[low] + (values[min(low + 1, len(values) - 1)] - values[low]) * (index - low)
            q1, q3, median = box.get('q1', quantile(.25)), box.get('q3', quantile(.75)), box.get('median', quantile(.5))
            if not all(finite(v) for v in (q1, q3, median)) or q3 < q1:raise ValueError('Invalid box quartiles.')
            lo = box.get('low', next((v for v in values if v >= q1 - 1.5 * (q3-q1)), values[0]))
            hi = box.get('high', next((v for v in reversed(values) if v <= q3 + 1.5 * (q3-q1)), values[-1]))
            mean = box.get('mean')
            if not all(finite(v) for v in (lo, hi)) or mean is not None and not finite(mean):raise ValueError('Invalid box whiskers or mean.')
            mild = box.get('mildOutliers', box.get('outliers', [v for v in values if v < lo or v > hi]))
            extreme = box.get('extremeOutliers', [])
            if any(not isinstance(out, list) or len(out) > MAX_CELLS or any(not finite(v) for v in out) for out in (mild, extreme)):raise ValueError('Invalid box outliers.')
            extents.extend([*values,q1,q3,median,lo,hi,*mild,*extreme]+([mean] if mean is not None else []))
            x = i + .5
            base = {**series,'type':'line','markers':{'visible':False}}
            lines.append({**base,'x':[x,x,None,x-width/3,x+width/3,None,x-width/3,x+width/3,None,x-width/2,x-width/2,x+width/2,x+width/2,x-width/2], 'y':[lo,hi,None,lo,lo,None,hi,hi,None,q1,q3,q3,q1,q1]})
            for label,value,color in [('Median',median,'#2563eb'),('Mean',mean,'#dc2626')]:
                if value is not None:lines.append({**base,'name':str(series.get('name','Group'))+' · '+label,'x':[x-width/2,x+width/2],'y':[value,value],'color':color,'width':2})
            if mild:lines.append({**base,'name':str(series.get('name','Group'))+' · Mild outliers','type':'scatter','x':[x]*len(mild[:1000]),'y':mild[:1000],'markers':{'visible':True,'style':'nofill','radius':3}})
            # Native marker type contracts are version-specific. Use XY strokes
            # for extreme-outlier asterisks instead of guessing a marker enum.
            if extreme:
                dy = max(max(extents)-min(extents), 1) / 80;dx=len(raw)/150
                xs,ys=[],[]
                for y in extreme[:1000]:
                    xs.extend([x-dx,x+dx,None,x-dx,x+dx,None,x,x,None]);ys.extend([y-dy,y+dy,None,y+dy,y-dy,None,y-dy,y+dy,None])
                lines.append({**base,'name':str(series.get('name','Group'))+' · Extreme outliers','x':xs,'y':ys,'width':1})
            ticks.append({'value':x,'label':str(series.get('name','Group'))})
        if not lines:raise ValueError('A box plot requires finite values.')
        result={**chart,'type':'line','series':lines,'xTicks':ticks,'xMin':0,'xMax':len(raw),'legend':False}
        return result, 'Box plots export as editable XY outlines, whiskers, medians, means and outlier geometry; translucent fill is omitted.'
    if chart.get('type') == 'histogram':
        converted, changed = [], False
        for series in raw:
            if not isinstance(series, dict):raise ValueError('Invalid histogram series.')
            if series.get('type', 'histogram') != 'histogram':converted.append(series);continue
            ys=series.get('y');edges=series.get('binEdges',chart.get('binEdges'))
            if not isinstance(ys,list) or not ys or not isinstance(edges,list) or len(edges)!=len(ys)+1 or not all(finite(v) for v in edges) or any(b<=a for a,b in zip(edges,edges[1:])):raise ValueError('Invalid histogram boundaries.')
            widths=[b-a for a,b in zip(edges,edges[1:])]
            changed = changed or not all(math.isclose(v,widths[0],rel_tol=1e-9,abs_tol=1e-12) for v in widths)
            xs,values=[],[]
            for i,y in enumerate(ys):
                if y is None:continue
                if not finite(y):raise ValueError('Invalid histogram value.')
                xs.extend([edges[i],edges[i],edges[i+1],edges[i+1],None]);values.extend([0,y,y,0,None])
            converted.append({**series,'type':'line','x':xs,'y':values,'markers':{'visible':False}})
        if changed:
            result={**chart,'type':'line','series':converted}
            # An irregular category axis would distort the exact numeric bins.
            result.pop('xTicks',None)
            return result, 'Unequal histogram bins export with exact numeric boundaries as editable outlines; fill and custom category labels are omitted.'
    return chart, None


def _export_chart(entry, sheet_index, original=None, original_chart=None):
    """Map supported independent charts to the observed native chart fields."""
    chart, position = entry.get("chart"), entry.get("position", {})
    if not isinstance(chart, dict) or not isinstance(position, dict):
        raise ValueError("Invalid worksheet chart metadata.")
    if original_chart is None or chart != original_chart:
        mapped, note = _chart_geometry(chart)
        if note:
            mapped_entry = {**entry, 'chart':mapped}
            converted, warning = _export_chart(mapped_entry, sheet_index)
            if converted is not None:converted['statworkbenchSourceChart'] = copy.deepcopy(chart)
            return converted, warning or note
    kind = chart.get("type")
    if kind not in {"line", "spline", "step", "scatter", "bar", "histogram"}:
        return None, f"Chart {chart.get('title', 'Untitled')!r}: unsupported {kind!r} chart remains in Save Project."
    raw = chart.get("series")
    if not isinstance(raw, list) or not raw or len(raw) > 1000:
        raise ValueError("Invalid worksheet chart series.")
    output = copy.deepcopy(original) if isinstance(original, dict) else {}
    options = output.setdefault("options", {})
    if not isinstance(options, dict):options = output["options"] = {}
    options.update(row=_integer(position.get("row", 0), "chart row", maximum=MAX_ROWS - 101), col=_integer(position.get("column", 0), "chart column", maximum=MAX_COLUMNS - 1))
    for dimension, default, minimum in (("width", 680, 160), ("height", 420, 100)):
        value = position.get(dimension, default)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not minimum <= value <= 2000:
            raise ValueError("Invalid worksheet chart size.")
        options[dimension] = value
    # Pixel dimensions supersede the old occupied-cell dimensions after resizing.
    options.pop("cwidth", None);options.pop("cheight", None)
    if original_chart is not None and chart == original_chart:
        output["sheetIndex"] = sheet_index
        return output, None
    options.update(title=str(chart.get("title", "Chart")), legend=3 if chart.get("legend", True) else 0)
    axes = options.setdefault("axis", {})
    if not isinstance(axes, dict):axes = options["axis"] = {}
    for axis in ("x", "y"):
        values = axes.setdefault(axis, {})
        if not isinstance(values, dict):values = axes[axis] = {}
        for native, key in (("label", axis + "Label"), ("min", axis + "Min"), ("max", axis + "Max"), ("majorunit", axis + "MajorUnit")):
            values.pop(native, None)
            if key in chart:
                value = chart[key]
                if native == "label":values[native] = str(value)
                elif not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value) and (native != "majorunit" or value > 0):values[native] = value
                else:raise ValueError("Invalid worksheet chart axis.")
        options["revertAxis" + axis.upper()] = chart.get("reverse" + axis.upper()) is True
    axes["x"].pop("categories", None)
    categories = []
    for series in raw:
        if not isinstance(series, dict) or not isinstance(series.get("y"), list) or not series["y"]:
            raise ValueError("Invalid worksheet chart data.")
        for x in series.get("x", []):
            if isinstance(x, str) and x not in categories:categories.append(x)
    ticks = chart.get("xTicks")
    if categories:
        axes["x"]["categories"] = categories
        axes["x"].setdefault("min", 0);axes["x"].setdefault("max", len(categories))
    elif isinstance(ticks, list) and ticks:
        if any(not isinstance(t, dict) or not isinstance(t.get("label"), str) or not isinstance(t.get("value"), (int, float)) or not math.isfinite(t["value"]) for t in ticks):
            raise ValueError("Invalid worksheet chart category labels.")
        # Native category labels are evenly spaced; reject arbitrary tick maps.
        gaps = [b["value"] - a["value"] for a, b in zip(ticks, ticks[1:])]
        if gaps and (gaps[0] <= 0 or any(not math.isclose(gap, gaps[0], rel_tol=1e-9, abs_tol=1e-12) for gap in gaps)):
            return None, f"Chart {chart.get('title', 'Untitled')!r}: irregular category labels remain in Save Project."
        axes["x"]["categories"] = [t["label"] for t in ticks]
    converted = []
    palette = ["#4869df", "#28a494", "#e3a64f", "#b274ca", "#d96d80", "#579bc1"]
    for index, series in enumerate(raw):
        subtype = series.get("type", kind)
        if subtype not in {"line", "spline", "step", "scatter", "bar", "histogram"}:
            return None, f"Chart {chart.get('title', 'Untitled')!r}: unsupported {subtype!r} series remains in Save Project."
        y = series["y"]
        x = series.get("x", list(range(1, len(y) + 1)))
        if not isinstance(x, list) or len(x) != len(y) or any(v is not None and (isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)) for v in y):
            raise ValueError("Invalid worksheet chart data.")
        if categories:
            if any(v is not None and (not isinstance(v, str) or v not in categories) for v in x):
                return None, f"Chart {chart.get('title', 'Untitled')!r}: mixed numeric/text coordinates remain in Save Project."
            x = [categories.index(v) + 0.5 if v is not None else None for v in x]
        elif any(v is not None and (isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)) for v in x):
            raise ValueError("Invalid worksheet chart coordinates.")
        if subtype == "histogram":
            edges = series.get("binEdges", chart.get("binEdges"))
            if not isinstance(edges, list) or len(edges) != len(y) + 1 or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in edges):
                raise ValueError("Invalid worksheet histogram boundaries.")
            widths = [b - a for a, b in zip(edges, edges[1:])]
            if widths[0] <= 0 or any(not math.isclose(v, widths[0], rel_tol=1e-9, abs_tol=1e-12) for v in widths):
                return None, f"Chart {chart.get('title', 'Untitled')!r}: unequal histogram widths remain in Save Project."
            subtype = "bar"
            axes["x"].setdefault("min", edges[0]);axes["x"].setdefault("max", edges[-1])
        prior_series = options.get("series", [])
        target = copy.deepcopy(prior_series[index]) if isinstance(prior_series, list) and index < len(prior_series) and isinstance(prior_series[index], dict) else {}
        target.update(label=str(series.get("name", "Series")), type=subtype, x=x, y=copy.deepcopy(y), color=_color(series.get("color")) or palette[index % len(palette)])
        target.pop("dashStyle", None);target.pop("line-style", None)
        if series.get("dash"):
            if series["dash"] != "dash":
                return None, f"Chart {chart.get('title', 'Untitled')!r}: unsupported line dash pattern remains in Save Project."
            target["line-style"] = "dash"
        if subtype == "bar":
            target["width"] = series.get("barWidth", 95)
            target["bar-style"] = {"normal": "stacked", "percent": "percentstack"}.get(chart.get("stack"), "clustered")
            if chart.get("stack") and (not axes['x'].get('categories') or any(s.get("type", kind) != "bar" for s in raw)):
                return None, f"Chart {chart.get('title', 'Untitled')!r}: this stacked chart layout remains in Save Project."
        else:
            target.pop("bar-style", None)
            target["width"] = series.get("width", 2.25)
        width = target["width"]
        if isinstance(width, bool) or not isinstance(width, (int, float)) or not math.isfinite(width) or not 0 < width <= (100 if subtype == "bar" else 12):
            raise ValueError("Invalid worksheet chart line/bar width.")
        markers = series.get("markers", {})
        if not isinstance(markers, dict):raise ValueError("Invalid worksheet chart markers.")
        preserved_markers = target.get("markers", {})
        target["markers"] = copy.deepcopy(preserved_markers) if isinstance(preserved_markers, dict) else {}
        target["markers"].update(visible=markers.get("visible", subtype == "scatter" or len(y) < 45), r=markers.get("radius", 3 if subtype == "scatter" else 2.2))
        target["markers"].setdefault("type", "circle")
        target["markers"].pop("style", None)
        if not isinstance(target["markers"]["visible"], bool) or isinstance(target["markers"]["r"], bool) or not isinstance(target["markers"]["r"], (int, float)) or not 1 <= target["markers"]["r"] <= 20:
            raise ValueError("Invalid worksheet chart marker appearance.")
        if markers.get("style") == "nofill":target["markers"]["style"] = "nofill"
        converted.append(target)
    options["series"] = converted
    # Native chart readers expect the statistical engine to supply domains.
    # Reproduce the independent renderer's automatic domain when no override
    # is present, including zero and cumulative heights for bar charts.
    y_values = [v for series in converted for v in series['y'] if v is not None]
    x_values = [v for series in converted for v in series['x'] if v is not None]
    if not y_values or not x_values:raise ValueError('The exported chart has no finite points.')
    is_bar = any(series['type'] == 'bar' for series in converted)
    if chart.get('stack'):
        if any(v < 0 for v in y_values):
            return None, f"Chart {chart.get('title', 'Untitled')!r}: stacked negative values remain in Save Project."
        heights = {}
        for series in converted:
            for x, y in zip(series['x'], series['y']):
                if x is not None and y is not None:heights[x] = heights.get(x, 0) + y
        y_values = [0, 100] if chart['stack'] == 'percent' else [0, *heights.values()]
    low, high = min(y_values), max(y_values)
    if is_bar:low, high = min(0, low), max(0, high)
    if low == high:low, high = low - 1, high + 1
    padding = (high - low) * .08
    high += padding
    if not is_bar:low -= padding
    axes['y'].setdefault('min', low);axes['y'].setdefault('max', high)
    low, high = min(x_values), max(x_values)
    if is_bar and kind != 'histogram' and not categories:
        unique = sorted(set(x_values));gaps = [b - a for a,b in zip(unique,unique[1:])]
        step = min(gaps) if gaps else 1
        low -= step/2;high += step/2
    if low == high:low, high = low - .5, high + .5
    axes['x'].setdefault('min', low);axes['x'].setdefault('max', high)
    if any(not math.isfinite(axes[axis][key]) for axis in ('x','y') for key in ('min','max')):
        raise ValueError('The exported chart bounds exceed the numeric range.')
    output["sheetIndex"] = sheet_index
    return output, None


def serialize_workbook(snapshot):
    """Export current cells/layout into the observed SPJS JSON container.

    Unknown imported metadata is carried through. This serializer does not run
    formulas, infer analysis parameters, or copy native program code.
    """
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("sheetOrder"), list) or not isinstance(snapshot.get("sheets"), dict):
        raise ValueError("SPJS export requires a workbook snapshot.")
    order = snapshot["sheetOrder"]
    if not 1 <= len(order) <= 100 or any(not isinstance(key, str) for key in order) or len(set(order)) != len(order):
        raise ValueError("Invalid SPJS worksheet order.")
    provenance = snapshot.get("custom", {}).get("statplusImport", {})
    if not isinstance(provenance, dict):
        provenance = {}
    source = copy.deepcopy(provenance.get("workbookMetadata", {}))
    document = copy.deepcopy(provenance.get("documentMetadata", {}))
    if not isinstance(source, dict) or not isinstance(document, dict):
        raise ValueError("Invalid original-project metadata.")
    source.update(version=source.get("version", "9.40.20161.0"), sheetCount=len(order), sheets={})
    styles = snapshot.get("styles", {})
    image_registry = snapshot.get('custom', {}).get('statworkbenchImages')
    image_warnings = []
    if image_registry is not None and (not isinstance(image_registry, list) or len(image_registry) > 1000 or any(not isinstance(entry, dict) for entry in image_registry)):
        raise ValueError('Invalid worksheet picture registry.')
    named = {s["name"]: s for s in source.get("namedStyles", []) if isinstance(s, dict) and isinstance(s.get("name"), str)}
    def resolve_style(value):
        return styles.get(value, {}) if isinstance(value, str) else value
    count = 0
    for index, identifier in enumerate(order):
        sheet = snapshot["sheets"].get(identifier)
        if not isinstance(sheet, dict) or not isinstance(sheet.get("name"), str):
            raise ValueError("Invalid SPJS worksheet.")
        original = sheet.get("custom", {}).get("statplusImport", {})
        native = copy.deepcopy(original) if isinstance(original, dict) else {}
        _export_images(native, identifier, image_registry, image_warnings)
        row_count = _integer(sheet.get("rowCount"), "row count", 1, MAX_ROWS)
        col_count = _integer(sheet.get("columnCount"), "column count", 1, MAX_COLUMNS)
        native.update(name=sheet["name"], index=index, rowCount=row_count, columnCount=col_count, showGridLine=sheet.get("showGridlines", 1) != 0)
        data = copy.deepcopy(sheet.get("custom", {}).get("statplusDataMetadata", {}))
        if not isinstance(data, dict):
            data = {}
        data["dataTable"] = {}
        cells = sheet.get("cellData", {})
        if not isinstance(cells, dict):
            raise ValueError("Invalid SPJS worksheet cells.")
        for row_key, row in cells.items():
            _index(row_key, "row", row_count)
            if not isinstance(row, dict):
                raise ValueError("Invalid SPJS worksheet row.")
            for col_key, cell in row.items():
                _index(col_key, "column", col_count)
                if cell is None:
                    continue
                if not isinstance(cell, dict):
                    raise ValueError("Invalid SPJS worksheet cell.")
                count += 1
                if count > MAX_CELLS:
                    raise ValueError("The SPJS workbook exceeds the stored cell limit.")
                prior = cell.get("custom", {}).get("statplusImport", {})
                prior = prior if isinstance(prior, dict) else {}
                output = copy.deepcopy(prior.get("metadata", {}))
                if not isinstance(output, dict):
                    output = {}
                # Intact groups are restored after all current cells are written;
                # individually edited cells remain independent live formulas.
                output.pop("statworkbenchArray", None)
                value = cell.get("v")
                if value is not None:
                    if not isinstance(value, (str, bool, int, float)) or isinstance(value, (int, float)) and not math.isfinite(value):
                        raise ValueError("Invalid SPJS cell value.")
                    output["value"] = value
                formula = cell.get("f")
                if formula is not None:
                    if not isinstance(formula, str) or len(formula) > MAX_CELL_CHARACTERS:
                        raise ValueError("Invalid SPJS formula text.")
                    if formula == prior.get("translatedFormula"):
                        formula = prior.get("formula", formula)
                    if formula == "=NA()" and prior.get("formulaStatus") == "unsupported":
                        # Keep unavailable formulas as errors, not stale caches.
                        output["statworkbenchOriginalFormula"] = prior.get("formula")
                    output["formula"] = formula.removeprefix("=")
                raw_style = prior.get("style")
                if isinstance(raw_style, str):
                    raw_style = named.get(raw_style, {})
                if "s" in cell:
                    output["style"] = _export_style(resolve_style(cell["s"]), raw_style)
                if output:
                    data["dataTable"].setdefault(row_key, {})[col_key] = output
        _restore_array_groups(cells, data['dataTable'], image_warnings)
        data.setdefault("defaultDataNode", {})["style"] = _export_style(resolve_style(sheet.get("defaultStyle", {})), data.get("defaultDataNode", {}).get("style"))
        native["data"] = data
        native["spans"] = [{"row": m["startRow"], "col": m["startColumn"], "rowCount": m["endRow"] - m["startRow"] + 1, "colCount": m["endColumn"] - m["startColumn"] + 1} for m in sheet.get("mergeData", [])]
        for key, target, dimension, limit in (("rowData", "rows", "h", row_count), ("columnData", "columns", "w", col_count)):
            prior_axis = native.get(target, {})
            if isinstance(prior_axis, list):
                prior_axis = {str(i): v for i, v in enumerate(prior_axis) if i < limit and isinstance(v, dict)}
            axis = {str(i): copy.deepcopy(v) for i, v in prior_axis.items() if str(i).isdigit() and int(i) < limit and isinstance(v, dict)} if isinstance(prior_axis, dict) else {}
            for axis_index, setting in sheet.get(key, {}).items():
                _index(axis_index, "axis", limit)
                if not isinstance(setting, dict):
                    raise ValueError("Invalid SPJS axis metadata.")
                axis.setdefault(axis_index, {})["visible"] = setting.get("hd", 0) != 1
                if dimension in setting:
                    axis[axis_index]["size"] = setting[dimension]
                if "s" in setting:
                    axis[axis_index]["style"] = _export_style(resolve_style(setting["s"]))
            native[target] = axis
        source["sheets"][sheet["name"]] = native
    active = snapshot.get("custom", {}).get("statworkbenchActiveSheetId")
    source["activeSheetIndex"] = order.index(active) if active in order else 0
    charts = copy.deepcopy(provenance.get("charts", []))
    ids = provenance.get("chartSheetIds", [])
    if not isinstance(charts, list) or not isinstance(ids, list):
        raise ValueError("Invalid original-project chart metadata.")
    retained_charts = []
    registry = snapshot.get("custom", {}).get("statworkbenchCharts")
    if registry is not None and (not isinstance(registry, list) or len(registry) > 1000):
        raise ValueError("Invalid worksheet chart registry.")
    managed = provenance.get("managedChartIndices", []) if registry is not None else []
    if not isinstance(managed, list) or any(isinstance(i, bool) or not isinstance(i, int) or not 0 <= i < len(charts) for i in managed):
        raise ValueError("Invalid original-project chart registry.")
    registered = set()
    if registry is not None:
        for entry in registry:
            if not isinstance(entry, dict):raise ValueError("Invalid worksheet chart registry entry.")
            index = entry.get("originalIndex")
            if index is not None:
                if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(charts) or index in registered:
                    raise ValueError("Invalid or duplicate original chart index.")
                registered.add(index)
    original_ids = {snapshot["sheets"][identifier].get("custom", {}).get("statplusImport", {}).get("index"): identifier for identifier in order}
    for index, chart in enumerate(charts):
        if index in managed or index in registered:
            continue
        identifier = ids[index] if index < len(ids) else original_ids.get(chart.get("sheetIndex")) if isinstance(chart, dict) else None
        if identifier is not None and identifier not in order:
            continue
        if identifier in order and isinstance(chart, dict):
            chart["sheetIndex"] = order.index(identifier)
        retained_charts.append(chart)
    warnings = copy.deepcopy(document.get("statworkbenchExportWarnings", []))
    omitted = copy.deepcopy(document.get("statworkbenchUnsupportedCharts", []))
    if not isinstance(warnings, list) or not all(isinstance(w, str) for w in warnings) or not isinstance(omitted, list):
        raise ValueError("Invalid retained chart export metadata.")
    warnings.extend(image_warnings)
    points = 0
    for entry in registry or []:
        identifier = entry.get("sheetId")
        if identifier not in order:
            continue
        chart = entry.get("chart")
        if not isinstance(chart, dict):raise ValueError("Invalid worksheet chart definition.")
        if not isinstance(chart.get("series", []), list):raise ValueError("Invalid worksheet chart series.")
        for series in chart.get("series", []):
            if isinstance(series, dict) and isinstance(series.get("y"), list):points += len(series["y"])
        if points > MAX_CELLS:raise ValueError("The worksheet chart points exceed supported limits.")
        original_index = entry.get("originalIndex")
        original = charts[original_index] if original_index is not None else None
        original_chart = None
        if isinstance(original, dict):
            translated = _charts([original], {original.get("sheetIndex"): identifier}, snapshot["sheets"], [])
            if translated:original_chart = translated[0]["chart"]
        converted, warning = _export_chart(entry, order.index(identifier), original, original_chart)
        if warning:warnings.append(warning)
        if converted is None:omitted.append(copy.deepcopy(entry))
        else:retained_charts.append(converted)
    # Unknown native fields remain inert. Unsupported independent chart types
    # are retained explicitly rather than masquerading as a different plot.
    document.pop("statworkbenchExportWarnings", None)
    document.pop("statworkbenchUnsupportedCharts", None)
    if warnings:
        document["statworkbenchExportWarnings"] = warnings
        document["statworkbenchUnsupportedCharts"] = omitted
    document.update(workbook=source, charts=retained_charts)
    # Re-use the import boundary for dimensions, names, merges and formulas.
    if len(source["sheets"]) != len(order):
        raise ValueError("Duplicate SPJS worksheet names.")
    translate_workbook(document, snapshot.get("name", "Workbook"), next(iter(source["sheets"])), lambda value: value)
    if len(json.dumps(document, ensure_ascii=False, allow_nan=False).encode("utf-8")) > MAX_FILE_BYTES:
        raise ValueError("The exported file exceeds the 64 MiB limit.")
    return document
