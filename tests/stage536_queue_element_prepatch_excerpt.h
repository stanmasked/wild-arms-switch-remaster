// Extracted QueueElement excerpt from PCSX-Redux cdrom.h at commit
// de4a33e9a69abec4f567ae33567537f867dc2bba; GPL-2.0-or-later.
    struct QueueElement {
        uint8_t payload[16];
        uint8_t value;
        bool valueRead = false;
        bool hasValue = false;
        bool hitMax = false;
        uint8_t payloadSize = 0;
        uint8_t payloadIndex = 0;
        bool isPayloadAtEnd() const { return payloadIndex == payloadSize; }
        bool isPayloadEmpty() const { return (payloadSize == 0) || hitMax; }
        bool isPayloadFull() const { return payloadSize == sizeof(payload); }
        bool empty() const { return valueEmpty() && isPayloadEmpty(); }
        bool valueEmpty() const { return !hasValue || valueRead; }
        void clear() {
            hasValue = false;
            valueRead = false;
            payloadSize = 0;
            payloadIndex = 0;
        }
        void setValue(uint8_t newValue) {
            value = newValue;
            hasValue = true;
        }
        void setValue(Cause cause) { setValue(static_cast<uint8_t>(cause)); }
        void pushPayloadData(uint8_t value) {
            if (payloadSize < sizeof(payload)) payload[payloadSize++] = value;
        }
        void pushPayloadData(std::string_view values) {
            for (auto value : values) {
                pushPayloadData(value);
            }
        }
        uint8_t getValue() const { return valueRead ? 0 : value; }
        uint8_t readPayloadByte() {
            while (payloadIndex >= 16) payloadIndex -= 16;
            uint8_t r = 0;
            if (payloadIndex < payloadSize) {
                r = payload[payloadIndex];
            }
            if (++payloadIndex == payloadSize) hitMax = true;
            return r;
        }
    };
