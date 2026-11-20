global-incdirs-y += ..
global-incdirs_ext-y += $(MODEL_DIR)
srcs-y += secure_ta.c
srcs-y += runtime_ta.c
cflags-runtime_ta.c-y += -O2 -ffp-contract=off
