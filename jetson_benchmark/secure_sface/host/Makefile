CC ?= cc
MODEL_DIR ?= $(abspath ../generated)
CFLAGS ?= -O2 -Wall -Wextra -Werror
CPPFLAGS += -I.. -I$(MODEL_DIR) -I$(OPTEE_CLIENT_EXPORT)/include
LDFLAGS += -L$(OPTEE_CLIENT_EXPORT)/lib

libsecure_sface.so: bridge.c ../protocol.h $(MODEL_DIR)/model.h
	$(CC) $(CPPFLAGS) $(CFLAGS) -shared -fPIC bridge.c $(LDFLAGS) -lteec -o $@
