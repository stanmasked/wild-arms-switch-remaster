"""Map caller-provided packed PS1 Q12 sin/cos entries into bounded memory.

The game table is NOT distributed here. Entries contain signed 16-bit sine
in the low half and cosine in the high half, indexed by 12-bit angle.
"""
import struct
try:
    from .mips_fixed32 import sign_extend16
    from .mips_memory_sequence import Memory
except ImportError:
    from mips_fixed32 import sign_extend16
    from mips_memory_sequence import Memory

ENTRY_COUNT=4096
ENTRY_BYTES=4
Q12=4096

def decode_entry(packed):
    return sign_extend16(packed),sign_extend16(packed>>16)

def index_angle(angle):
    return angle & (ENTRY_COUNT-1)

def entry_address(base,angle):
    if base<0 or base&3:
        raise ValueError('unaligned or negative table address')
    return base+ENTRY_BYTES*index_angle(angle)

def table_memory(base, packed_bytes):
    if base<0 or base&3:
        raise ValueError('unaligned or negative table address')
    if len(packed_bytes)!=ENTRY_COUNT*ENTRY_BYTES:
        raise ValueError('expected exactly 4096 packed entries')
    return Memory(base,packed_bytes)

def read_entry(memory,angle):
    addr=entry_address(memory.base,angle)
    packed=memory.read(addr,4)
    return decode_entry(packed)

def synthetic_cardinal_table():
    """Test-only sparse cardinal values, not the game's original data."""
    data=bytearray(ENTRY_COUNT*ENTRY_BYTES)
    samples={0:(0,Q12),1024:(Q12,0),2048:(0,-Q12),3072:(-Q12,0)}
    for angle,(sin,cos) in samples.items():
        struct.pack_into('<HH',data,angle*4,sin&65535,cos&65535)
    return bytes(data)
