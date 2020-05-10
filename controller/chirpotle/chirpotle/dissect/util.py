from typing import List, Optional, Sequence
from math import log, ceil
from Cryptodome.Cipher import AES
from Cryptodome.Hash import CMAC

def hexToStr(h):
  if isinstance(h, int):
    return ('0' if h < 0x10 else '') + hex(h)[2:]
  elif isinstance(h, Sequence):
    return " ".join(hexToStr(i) for i in h)
  else:
    return ""

def getWithMask(val, mask):
  """
  Applies mask to val and returns the result bit-shifted

  :param val: The one-byte-value to use
  :param mask: The mask to apply
  """
  # Get amount of zeros on the right side of the mask, meaning the index of the LSB
  lsbIdx = (mask&-mask).bit_length() - 1
  # Apply mask and shift right
  return (val & mask) >> lsbIdx

def setWithMask(baseVal, newVal, mask):
  """
  Applies mask to baseVal and changes the affected bits using newVal.

  Example:
    Mask:    0b11100000
    baseVal: 0b00101010
    newVal:    101      (-> 0b00000101)
    result:  0b10101010

  :param baseVal: the base value that is used for the non-masked bits
  :param val: the new value, that will be shifted to the masked area and applied to baseVal
  :param mask: the mask to use
  """
  # Allow bools for single-bit-values
  if (type(newVal) == bool):
    newVal = 1 if newVal == True else 0
  # Get amount of zeros on the right side of the mask, meaning the index of the LSB
  lsbIdx = (mask&-mask).bit_length() - 1
  # Zero-out the bits in baseVal, and logially or them with the shifted new bits
  return (baseVal & (mask ^ 0xff)) | ((newVal << lsbIdx) & mask)

def replaceBytes(base, offset, length, newData, checkLength = False, switchEndian = False):
  """
  Replaces the bytes from offset to offset + length in sequence base with the sequence of bytes in newData.

  Will raise a TypeError if base or newData aren't a sequence, a ValueError if newData contains values that
  are not within the byte range from 0 to 255 and

  :param base: The base sequence of bytes
  :param offset: The beginning of the part to be replaced
  :param length: The length of the part to be replaced
  :param newData: The new data
  :param checkLength: Whether to check if newData has the same length as the part to be replaced. (default: false)
  :param switchEndian: Switches endianess of newData (default: false)
  """
  if not isinstance(base, Sequence):
    raise TypeError("base must be a sequence")
  base = base if isinstance(base,list) else list(base)

  if not isinstance(newData, Sequence):
    raise TypeError("newData must be a sequence")

  if not isinstance(offset,int) or not isinstance(length,int):
    raise TypeError("offset and length must be int")
  if offset<0 or length<0 or (offset+length)>len(base):
    raise IndexError("offset are out of range for base ("+str(offset)+":"+str(offset+length)+")")

  if next((True for b in newData if b < 0 or b > 255), False):
    raise ValueError("Values in newData must be in the byte range (0..255)")

  if checkLength and len(newData)!=length:
    raise ValueError("newData has wrong length. Expected: " + str(length) + ", " + str(len(newData)) + " given.")

  if not switchEndian:
    return base[:offset] + (newData if isinstance(newData,list) else list(newData)) + base[offset+length:]
  else:
    return base[:offset] + list(reversed(newData)) + base[offset+length:]

def extractBytes(base, offset, length, assureReadonly = False, switchEndian = False):
  """
  Gets byte subsequence out of the byte sequence base, based on the offset and the length.

  :param base: The byte sequence to extract data from
  :param offset: The offset to read from
  :param length: The amount of bytes to read
  :param assureReadonly: Will return a tuple no matter what base is (default: false)
  :param switchEndian: Will reverse the byte order before returning (default: false)
  """
  if not isinstance(base, Sequence):
    raise TypeError("base must be a sequence")

  if not isinstance(offset,int) or not isinstance(length,int):
    raise TypeError("offset and length must be int")
  if offset<0 or length<0 or (offset+length)>len(base):
    raise IndexError("offset are out of range for base ("+str(offset)+":"+str(offset+length)+")")

  data = base[offset:length+offset]
  if switchEndian:
    return tuple(reversed(data)) if assureReadonly else (type(base))(reversed(data))
  else:
    return tuple(data) if assureReadonly else data

def numberToBytes(n: int, length: Optional[int] = None, littleEndian: bool = True) -> List[int]:
  """
  Converts a number to a sequence of bytes

  :param n: The number to convert
  :param length: Optional: The desired length of the byte sequence. If n does not fit, the msb will be cut.
  If length is None, it will be determined based on the value of n
  :param littleEndian: Returns the byte sequence in little endian order
  """
  # Auto-length if length == None
  if length is None:
    length = ceil(log(n, 256))

  bytesLE = [(n&(0xff<<(x*8)))>>(x*8) for x in range(length)]
  return list(bytesLE if littleEndian else reversed(bytesLE))

def replaceNumber(base, offset, length, n, isLittleEndian=True):
  """
  Replaces length bytes beginning from position offset in the byte sequence base with number n.

  The new data is returned.

  :param base: the byte sequence to be modified (new sequence will be returned)
  :param offset: beginning of the subsequence that should be replaced
  :param length: length of the sequence (so length=2 allows values from 0 to 0xffff)
  :param n: the value to write
  :param isLittleEndian: if true, the number will be written in little endian
  """
  # This will create the little endian notation of n as bytes.
  # If n is bigger than what would fit in the target sequence, the most significant bytes will be cut.
  data = numberToBytes(n, length, isLittleEndian)
  return replaceBytes(base, offset, length, data, checkLength=True)

def extractNumber(base, offset, length, isLittleEndian=True):
  """
  Extracts a multi-byte-integer from the byte sequence byte.

  :param base: The byte sequence to read from
  :param offset: The offset to begin reading
  :param length: The amount of bytes to consider
  :param isLittleEndian: If true, the source bytes will be considered to be little endian
  """
  data = extractBytes(base, offset, length, switchEndian=isLittleEndian)
  l = len(data)
  return sum(data[b]<<((l-b-1)*8) for b in range(l))

def freqToBytes(freq):
  """
  Converts a frequency in Hz to the 3-byte representation used in most MAC commands"
  """
  f = int(freq / 100)
  if f < 0 or f > 0xffffff:
    raise ValueError("frequency is out of range")
  return [
    (f & 0x0000ff),
    (f & 0x00ff00) >> 8,
    (f & 0xff0000) >> 16
  ]

def bytesToFreq(b):
  """
  Converts a sequence of 3 bytes from a MAC command to the actual frequency in Hz
  """
  if not isinstance(b, Sequence) or len(b)!=3 or next((True for x in b if x < 0 or x > 255), False):
    raise ValueError("frequency must be a 3 byte sequence")
  f = b[0] + (b[1] << 8) + (b[2] << 16)
  return f*100

def aes128_encrypt(key: Sequence[int], data: Sequence[int]) -> List[int]:
  """
  AES function as it's used in the LoRaWAN specification. Takes a block of 16 bytes as key,
  and 16 bytes as data and encrypts the data with the key.

  :param key: Key as sequence of bytes
  :param data: Data as sequence of bytes
  """
  if not isinstance(key, Sequence):
    raise TypeError("key must be a sequence of 16 bytes")
  if not isinstance(data, Sequence):
    raise TypeError("data must be a sequence of 16 bytes")

  if len(key)!=16 or next((True for k in key if k < 0 or k > 255),False):
    raise ValueError("key must be a sequence of 16 bytes")
  if len(data)!=16 or next((True for k in key if k < 0 or k > 255), False):
    raise ValueError("data must be a sequence of 16 bytes")
  # MODE_ECB as we encrypt only one segment anyway
  cipher = AES.new(bytes(key), AES.MODE_ECB)
  return [x for x in cipher.encrypt(bytes(data))]

def aes128_cmac(key: Sequence[int], data: Sequence[int]) -> List[int]:
  """
  AES function as it's used in the LoRaWAN specification. Takes a block of 16 bytes as key,
  and an arbitrary length of bytes as data and creates a 16 byte CMAC from it.

  :param key: Key as sequence of bytes
  :param data: Data as sequence of bytes
  """
  if not isinstance(key, Sequence):
    raise TypeError("key must be a sequence of 16 bytes")
  if not isinstance(data, Sequence):
    raise TypeError("data must be a sequence of bytes")
  if len(key)!=16 or next((True for k in key if k < 0 or k > 255),False):
    raise ValueError("key must be a sequence of 16 bytes")
  if next((True for k in key if k < 0 or k > 255), False):
    raise ValueError("data must be a sequence of 16 bytes")

  cmac = CMAC.new(bytes(key), ciphermod=AES)
  cmac.update(bytes(data))
  return [c for c in cmac.digest()]

class ListView(Sequence):
  """
  Provides a view on an underlying list from a start index to an end index.

  If the view is changed, this change is reflected in the underlying list and vice-versa.
  """
  def __init__(self, origin, start, stop=None, length=None, preserveLength=False):
    """
    Creates a new list view on origin[start:stop] or origin[start:start+length].

    At least one of the parameters stop or length has to be provided, with stop being the default
    when using positional arguments to match classic list indexing.

    :param origin: The list to base this view on
    :param start: The left offset in that base list
    :param stop: The right offset in that base list
    :param length: Alternative to passing stop: Length of the window in the base list.
    :param preserveLength: If set to true, the length of the data cannot be changed
    """
    if stop is None and length is None:
      raise ValueError("At least one of stop or length has to be provided")
    self._origin = origin
    self._offset = start
    self._length = stop - start if stop is not None else length
    self._preserveLength = preserveLength
    if self._offset < 0 or self._offset + self._length > len(self._origin):
      raise IndexError("[%d:%d] is not a valid index for the base list" %
        (self._offset, self._offset + self._length))

  def __len__(self):
    return self._length

  def _adjust_key(self, key):
    """
    Helper function to map a key (int or slice) to the value range of the origin
    """
    if isinstance(key, slice):
      start = 0 if key.start is None else key.start
      stop = self._length if key.stop is None else key.stop
      step = 1 if key.step is None else key.step
    else:
      start = key
      stop = key + 1
      step = 1
    # We check for > length to allow extending the view at the end with view[length:]=[...]
    if max(start, stop) > self._length or min(start, stop) < 0:
      raise IndexError("list index out of range: [%d:%d]" % (start,stop))
    return slice(start + self._offset, stop + self._offset, step)

  def __getitem__(self, key):
    if isinstance(key, slice):
      return self._origin[self._adjust_key(key)]
    else:
      return self._origin[self._adjust_key(key)][0]

  def __setitem__(self, key, value):
    if isinstance(key, slice):
      key = self._adjust_key(key)
      if self._preserveLength and (key.stop-key.start)//key.step != len(value):
        raise ValueError("Length cannot be changed")
      self._origin[key] = value
    else:
      self._origin[self._adjust_key(key)] = [value]

  def __delitem__(self, key):
    if self._preserveLength:
      raise ValueError("Length cannot be changed")
    if isinstance(key, slice):
      del self._origin[self._adjust_key(key)]
      self._length -= key.stop - key.start
    else:
      del self._origin[self._adjust_key(key)]
      self._length -= 1

  def __str__(self):
    return str(self._origin[self._offset : self._offset + self._length])

  def __repr__(self):
    return repr(self._origin[self._offset : self._offset + self._length])
