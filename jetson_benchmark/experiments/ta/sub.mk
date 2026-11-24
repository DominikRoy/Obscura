global-incdirs-y += ../../secure_sface ../../secure_sface/generated ../A ../C
srcs-y += experiment.c kernels.c
cflags-kernels.c-y += -O2 -ffp-contract=off
cflags-experiment.c-y += -O2 -ffp-contract=off
ifeq ($(EXPERIMENT_RPMB),y)
cflags-experiment.c-y += -DEXP_STORAGE=TEE_STORAGE_PRIVATE_RPMB
endif
