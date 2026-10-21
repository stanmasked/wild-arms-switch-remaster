# Standalone, synthetic Switch field prototype (requires devkitPro / switch-dev).
.SUFFIXES:

ifeq ($(strip $(DEVKITPRO)),)
$(error Set DEVKITPRO to the installed devkitPro directory)
endif

TOPDIR ?= $(CURDIR)
include $(DEVKITPRO)/libnx/switch_rules

TARGET   := wild_arms_field
BUILD    := build
SOURCES  := source
INCLUDES := ../include

ARCH     := -march=armv8-a+crc+crypto -mtune=cortex-a57 -mtp=soft -fPIE
CFLAGS   := -g -O2 -Wall -ffunction-sections $(ARCH) -D__SWITCH__ $(INCLUDE)
CXXFLAGS := $(CFLAGS) -std=gnu++20 -fno-rtti -fno-exceptions
# Only experimental NeXium builds can emit an auxiliary SD diagnostic file.
# Normal Switch NRO builds never define WA_NEXIUM_SAVE_TRACE.
ifeq ($(WA_NEXIUM_SAVE_TRACE),1)
CXXFLAGS += -DWA_NEXIUM_SAVE_TRACE=1
endif
# Never enable the experimental ARM training UI in ordinary NRO builds.
# Explicitly select make -C switch WA_ARM_EXPERIMENTAL=1 for a separate NRO.
ifeq ($(WA_ARM_EXPERIMENTAL),1)
CXXFLAGS += -DWA_ARM_EXPERIMENTAL=1
endif
# Opt-in manual preview of user's separately installed, private WAIC icon
# sheets. Never bundle art or change normal field/NeXium capture behavior.
ifeq ($(WA_PRIVATE_ICON_PREVIEW),1)
CXXFLAGS += -DWA_PRIVATE_ICON_PREVIEW=1
endif
ASFLAGS  := -g $(ARCH)
LDFLAGS  := -specs=$(DEVKITPRO)/libnx/switch.specs -g $(ARCH) -Wl,-Map,$(notdir $*.map)
LIBS     := -lnx
LIBDIRS  := $(LIBNX)
APP_TITLE   := Wild Arms Field Prototype
APP_AUTHOR  := RIKITU LAB
APP_VERSION := 0.1.0

ifneq ($(BUILD),$(notdir $(CURDIR)))
export OUTPUT := $(CURDIR)/$(TARGET)
export TOPDIR := $(CURDIR)
export VPATH := $(foreach dir,$(SOURCES),$(CURDIR)/$(dir))
export DEPSDIR := $(CURDIR)/$(BUILD)
CPPFILES := $(foreach dir,$(SOURCES),$(notdir $(wildcard $(dir)/*.cpp)))
export OFILES := $(CPPFILES:.cpp=.o)
export INCLUDE := $(foreach dir,$(INCLUDES),-I$(CURDIR)/$(dir)) \
  $(foreach dir,$(LIBDIRS),-I$(dir)/include) -I$(CURDIR)/$(BUILD)
export LIBPATHS := $(foreach dir,$(LIBDIRS),-L$(dir)/lib)
export LD := $(CXX)

.PHONY: all clean $(BUILD)
all: $(BUILD)
$(BUILD):
	@mkdir -p $(BUILD)
	@$(MAKE) --no-print-directory -C $(BUILD) -f $(CURDIR)/Makefile
clean:
	rm -rf $(BUILD) $(TARGET).nro $(TARGET).nacp $(TARGET).elf $(TARGET).map

else

.PHONY: all
DEPENDS := $(OFILES:.o=.d)
all: $(OUTPUT).nro
$(OUTPUT).nro: $(OUTPUT).elf $(OUTPUT).nacp
$(OUTPUT).elf: $(OFILES)
-include $(DEPENDS)

endif
