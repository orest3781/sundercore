"""Extract Character Ledger's saved JSON without executing the SavedVariables Lua."""
import json
import re
LONG_STRING = re.compile(rb'\[(=*)\[')
IDENTIFIER = re.compile(rb'[A-Za-z_][A-Za-z_0-9]*')
ASSIGNMENT = re.compile(rb'\s*=\s*')

def read_lua_literal(data: bytes, offset: int) -> tuple[str, int]:
    """Parse only a Lua string literal, never evaluate Lua code."""
    while offset < len(data) and data[offset:offset + 1].isspace():
        offset += 1
    long = LONG_STRING.match(data, offset)
    if long:
        start = offset + len(long.group())
        end = data.find(b"]" + long.group(1) + b"]", start)
        if end < 0:
            raise ValueError("Unterminated saved JSON string")
        raw = data[start:end]
        if raw.startswith(b"\r\n"):
            raw = raw[2:]
        elif raw.startswith(b"\n"):
            raw = raw[1:]
        return raw.decode("utf-8"), end + len(long.group(1)) + 2
    if data[offset:offset + 1] not in (b'"', b"'"):
        raise ValueError("The saved export is not a Lua string; run /charout save and /reload first")
    quote = data[offset]
    offset += 1
    out = bytearray()
    escapes = {ord("a"): 7, ord("b"): 8, ord("f"): 12, ord("n"): 10,
               ord("r"): 13, ord("t"): 9, ord("v"): 11,
               ord("\\"): 92, ord('"'): 34, ord("'"): 39}
    while offset < len(data):
        char = data[offset]
        offset += 1
        if char == quote:
            return out.decode("utf-8"), offset
        if char != 92:
            out.append(char)
            continue
        if offset >= len(data):
            break
        esc = data[offset]
        offset += 1
        if esc in escapes:
            out.append(escapes[esc])
        elif 48 <= esc <= 57:
            digits = bytearray([esc])
            while len(digits) < 3 and offset < len(data) and 48 <= data[offset] <= 57:
                digits.append(data[offset])
                offset += 1
            value = int(digits)
            if value > 255:
                raise ValueError("Invalid decimal escape in SavedVariables")
            out.append(value)
        elif esc == ord("x"):
            chunk = data[offset:offset + 2]
            if not re.fullmatch(rb"[0-9a-fA-F]{2}", chunk):
                raise ValueError("Invalid hexadecimal escape")
            out.append(int(chunk, 16))
            offset += 2
        elif esc == ord("z"):
            while offset < len(data) and data[offset:offset + 1].isspace():
                offset += 1
        elif esc in (10, 13):
            if esc == 13 and data[offset:offset + 1] == b"\n":
                offset += 1
            out.append(10)
        else:
            raise ValueError("Unexpected Lua escape in saved export")
    raise ValueError("Unterminated saved JSON string")


def read_lua_string(data: bytes, offset: int) -> str:
    return read_lua_literal(data, offset)[0]


def saved_literal(data: bytes) -> str:
    """Find the top-level assignment, skipping comments, strings, and table bodies."""
    pos, depth, found = 0, 0, None
    while pos < len(data):
        if data[pos:pos+2] == b'--':
            long = LONG_STRING.match(data, pos+2)
            if long:
                stop = data.find(b']'+long.group(1)+b']', pos+2+len(long.group()))
                if stop < 0: raise ValueError('Unterminated Lua comment')
                pos = stop+len(long.group(1))+2
            else:
                stop = data.find(b'\n', pos+2);pos = len(data) if stop < 0 else stop+1
            continue
        if data[pos:pos+1] in (b'"', b"'") or LONG_STRING.match(data,pos):
            _,pos=read_lua_literal(data,pos);continue
        token=IDENTIFIER.match(data,pos)
        if token:
            pos+=len(token.group())
            if token.group()==b'CharacterLedgerJSON' and depth==0:
                assignment=ASSIGNMENT.match(data,pos)
                if assignment:
                    found,pos=read_lua_literal(data,pos+len(assignment.group()))
                    suffix=data[pos:].lstrip(b' \t')
                    if suffix and not suffix.startswith((b'\r',b'\n',b';',b'--')):
                        raise ValueError('Saved JSON must be a literal, not a Lua expression')
            continue
        char=data[pos:pos+1]
        if char in (b'{',b'('):depth+=1
        elif char in (b'}',b')'):depth=max(0,depth-1)
        pos+=1
    if found is None:
        raise ValueError("No saved export yet. In game, use /charout save and then /reload.")
    return found


def extract(data: bytes) -> dict:
    result = json.loads(saved_literal(data), parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite JSON value')))
    if not isinstance(result, dict) or type(result.get("schemaVersion")) is not int or result.get("schemaVersion") != 1 or "character" not in result:
        raise ValueError("Unrecognized Character Ledger export schema")
    return result
