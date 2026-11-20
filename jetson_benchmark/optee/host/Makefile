CC ?= cc
CFLAGS ?= -O2 -Wall -Wextra -Werror
CPPFLAGS += -I$(OPTEE_CLIENT_EXPORT)/include
LDFLAGS += -L$(OPTEE_CLIENT_EXPORT)/lib

libobscura_tee.so: bridge.c ../obscura_ta.h
	$(CC) $(CPPFLAGS) $(CFLAGS) -shared -fPIC bridge.c $(LDFLAGS) -lteec -o $@
