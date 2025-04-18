import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from libfss.fss import (
    sampleBits,
    ICNew,
    GroupElement,
    FSS_RING_LEN,
    FSS_INPUT_LEN,
    FlexKey,
    CondEval,
)
from common.helper import *
from common.constants import *
import secrets


import pickle


class SemiHonestFSS:
    """
    SemiHonestFSS for (LOGICAL AND) computation with a IntCmp comparison result.
    """

    def __init__(self, seed=None, sec_para=128, ring_len=1):
        self.seed = seed
        self.sec_para = sec_para
        self.ring_len = ring_len
        self.refreshSeed()

    def refreshSeed(self):
        seed_bits = sampleBits(self.seed, self.sec_para * 2)
        self.seed = seed_bits & ((1 << self.sec_para) - 1)
        random.seed(self.seed)

    """
    Prepare FSS keys for the evaluation of c1, TODO: 64-bits random value should be provided
    """

    def genFirstKey(self):
        ic = ICNew(sec_para=self.sec_para, ring_len=1)
        beta = GroupElement(1, 1)
        r0, r1, k0, k1 = ic.keyGen(self.seed, FSS_INPUT_LEN, beta)
        return (r0, r1, k0.packData(), k1.packData())

    """
    Prepare condEval key pairs
    """

    def genSecondKey(self):
        ic = ICNew(sec_para=self.sec_para, ring_len=self.ring_len)
        fss2_whole_rValue = secrets.randbits(INPUT_BITS_LEN)
        truncated_fss2_rand = int(fss2_whole_rValue / TRUNCATE_FACTOR)
        r0, r1, k0, k1 = ic.keyGen(
            self.seed, FSS_INPUT_LEN, GroupElement(1, 1), given_rand=truncated_fss2_rand
        )
        ck0, ck1 = CondEval.genFromFssKeys([k0.packData(), k1.packData()])

        # r_Array = [r0, r1]
        # r_value,cipher,sk
        player0 = [r0, ck0[0], ck0[1]]
        player1 = [r1, ck1[0], ck1[1]]
        return (fss2_whole_rValue, player0, player1)


class Dealer:
    """This code emulates the behavior of a Trusted Service Provider. However, here would be the place to implement the OT or HE for computing and sharing the shares for the scalar product.
    1) Firstly it generates pseduorandom correlated randomness according to an specified circuit f.
    2) 
    """
    def __init__(self, index):
        """Instantiate PRFs to generate random offset"""
        self._index = index
        self.fss = SemiHonestFSS(seed=1234127)
        self.vec_s = convert_raw(ALL_DICT_DATA[ALL_LABELS[2 * index + 1]])
        self.vec_v = convert_raw(ALL_DICT_DATA[ALL_LABELS[2 * index]])
        #print(self.vec_v)
        self.vec_plain = plain_convert_raw(ALL_DICT_DATA[ALL_LABELS[2 * index]])

    # Generate offline phase correlated pseudorandom data specifically for circuit C.
    def genOffline(self):
        """Output the arithemtical sharing of pseudorandom data for online computation for the given cosine-similarity computation circuit C"""
        vec_len = len(self.vec_v)
        # Prepare-1. For inner-product (s \cdot v) input wire preparation, prepare random data for input wire
        in_s = self.gen_SS_tuple(INPUT_BITS_LEN, vec_len)
        in_v = self.gen_SS_tuple(INPUT_BITS_LEN, vec_len)
        #non_masked_value = self.vec_plain
        in_v_value = [val[0] for val in in_v]
        self.vec_v = vec_add(self.vec_v, in_v_value, SEMI_HONEST_MODULO)

        in_s_value = [v[0] for v in in_s]
        self.vec_s = vec_add(self.vec_s, in_s_value, SEMI_HONEST_MODULO)

        s_v = [
            self.gen_SS_with_Val(ring_mul(in_s[i][0], in_v[i][0], SEMI_HONEST_MODULO))
            for i in range(vec_len)
        ]
        s_s = [
            self.gen_SS_with_Val(ring_mul(in_s[i][0], in_s[i][0], SEMI_HONEST_MODULO))
            for i in range(vec_len)
        ]
        v_v = [
            self.gen_SS_with_Val(ring_mul(in_v[i][0], in_v[i][0], SEMI_HONEST_MODULO))
            for i in range(vec_len)
        ]

        # IMPORTANT!! k0,k1 being ic keys
        # MARK: ip_out denotes the random value by the output wire
        fss1keys = self.fss.genFirstKey()
        recover = fss1keys[0] + fss1keys[1]
        ip_out = self.gen_SS_with_Val(recover.getValue())
        # v2Bin = v[2].packData()
        # v3Bin = v[3].packData()
        # print("v2Bin len is: ", len(v2Bin))
        # print("v3Bin len is: ", len(v3Bin))
        # fss1keys.append((v2Bin, v3Bin))

        ################The 2nd fss offset preparation#################

        all_rValue,player0, player1 = self.fss.genSecondKey()
        r_mul_out = self.gen_SS_with_Val( all_rValue)

        fss2keys = [player0, player1]
        #################The 2nd fss offset preparation#################

        # Prepare-2.1 For square gate (s \cdot s, v \cdot v) square pair preparation
        ss_out = self.gen_SS_tuple(INPUT_BITS_LEN)
        vv_out = self.gen_SS_tuple(INPUT_BITS_LEN)

        # square gate, 2-input multiplication, using the first fss random offset
        ip2 = self.gen_SS_with_Val(ring_mul(ip_out[0], ip_out[0], SEMI_HONEST_MODULO))
        sv_product = self.gen_SS_with_Val(
            ring_mul(ss_out[0], vv_out[0], SEMI_HONEST_MODULO)
        )

        for i in range(2):
            _start = i + 1
            non_mask = [0] * vec_len
            in_v_drone = [0] * vec_len
            vv = 0
            if i == 0:
                non_mask = self.vec_plain
                print(non_mask)
                in_v_drone = in_v_value
                vv = vv_out[0]
           # print(i)
            server_correlated = [
                # Masked input data of client/bank
                self.vec_s,
                self.vec_v,
                non_mask,
                in_v_drone,
                ###First circuit layer###
                [v[_start] for v in in_s],
                [v[_start] for v in in_v],
                [v[_start] for v in s_v],
                [v[_start] for v in s_s],
                [v[_start] for v in v_v],
                ip_out[_start],
                # fss key
                fss1keys[i + 2],
                ss_out[_start],
                #vv_out[_start],
                vv,
                ###Used in second round###
                ip2[_start],
                sv_product[_start],
                r_mul_out[_start],
                # [(e[_start], e[_start + 1]) for e in sub_TruncateArr],
                fss2keys[i],
            ]

            parent_location = Path(__file__).resolve().parent.parent
            with open(
                parent_location
                / ("data/64/offline.pkl" + str(i) + "-" + str(self._index)),
                "wb",
            ) as file:
                pickle.dump(server_correlated, file)

    def gen_SS_tuple(self, nbits, _len=None):
        if _len is not None:
            ret = []
            for i in range(_len):
                v = secrets.randbits(nbits)
                v0 = secrets.randbits(INPUT_BITS_LEN)
                v1 = mod_sub(v, v0, SEMI_HONEST_MODULO)
                ret.append((v, v0, v1))
            return ret
        else:
            v = secrets.randbits(nbits)
            v0 = secrets.randbits(INPUT_BITS_LEN)
            v1 = mod_sub(v, v0, SEMI_HONEST_MODULO)
            return [v, v0, v1]

    def gen_SS_with_Val(self, val):
        v0 = secrets.randbits(INPUT_BITS_LEN)
        v1 = mod_sub(val, v0, SEMI_HONEST_MODULO)
        return [val, v0, v1]


if __name__ == "__main__":
    for i in range(BENCHMARK_TESTS_AMOUNT):
        dealer = Dealer(i)
        dealer.genOffline()
