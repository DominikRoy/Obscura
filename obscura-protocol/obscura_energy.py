import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))
sys.path.append('/home/noname/.local/lib/python3.9/site-packages')

from libfss.fss import (
    FSS_INPUT_LEN,
    FSS_RING_LEN,
    GroupElement,
    ICNew,
    NewICKey,
    CondEval,
)
from common.helper import *
from common.constants import *
import secrets
import time
import sys
import asyncio
from tno.mpc.communication import Pool
import pickle

"""
The code is from https://github.com/nann-cheng/CondEval, we adapted the code for obscura.
Please be aware this code is not meant for production.
Code without time measurements. This code is meant for powertop measurements.
"""
class Server:
    """A description of what the computing server does.
    1) It performs computation as decribed by a predefined circuit f.
    """

    def __init__(self, _id):
        self.id = _id
        self.circuit = {}
        self.sub_shares = []
        self.vec_s = None
        self.vec_v = None

        self.in_wire0 = None
        self.in_wire1 = None
        self.m_CondEval = None

    def receiveCircuit(self, all):
        for index, key in enumerate(CIRCUIT_TOPOLOGY_4_SEMI_HONEST):
            #print(index)
            #print(key)
            if key == "fss1":
                self.circuit[key] = NewICKey.unpack(all[index], 1)
            else:
                self.circuit[key] = all[index]

        self.vec_s = self.circuit["mask_vec_s"]
        self.vec_v = self.circuit["mask_vec_v"]
        self.m_CondEval = CondEval(1, self.circuit["fss2"][1], self.circuit["fss2"][2])

    def resetInputWires(self, w0, w1):
        self.in_wire0 = w0
        self.in_wire1 = w1

    def onMulGate(self, keys):
        ret = 0
        if self.id == 0:
            ret = ring_mul(self.in_wire1, self.in_wire0, SEMI_HONEST_MODULO)
        else:
            ret = 0
        ret = mod_sub(
            ret,
            ring_mul(self.in_wire1, self.circuit[keys[0]], SEMI_HONEST_MODULO),
            SEMI_HONEST_MODULO,
        )
        ret = mod_sub(
            ret,
            ring_mul(self.in_wire0, self.circuit[keys[1]], SEMI_HONEST_MODULO),
            SEMI_HONEST_MODULO,
        )
        ret = ring_add(ret, self.circuit[keys[2]], SEMI_HONEST_MODULO)
        self.sub_shares.append(ret)

    # A local operation realizing FSS offset addition as well as truncation operation
    def sub_Truncate_Fss(self, ipWire, ssWire, vvWire):
        # Step2-1. Square gate
        self.resetInputWires(ipWire, ipWire)
        self.onMulGate(["ip_out", "ip_out", "ip2"])

        # Step2-2. Mul gate & local sub
        self.resetInputWires(ssWire, vvWire)
        self.onMulGate(["ss_out", "vv_out", "sv_mul"])

        # a value scaling, b value scaling
        self.sub_shares[0] = ring_mul(A_SCALE, self.sub_shares[0], SEMI_HONEST_MODULO)
        self.sub_shares[1] = ring_mul(B_SCALE, self.sub_shares[1], SEMI_HONEST_MODULO)
        sub = mod_sub(self.sub_shares[0], self.sub_shares[1], SEMI_HONEST_MODULO)
        sub = ring_add(sub, self.circuit["sub_Truncate"], SEMI_HONEST_MODULO)

        return sub
        # return self.circuit["sub_Truncate"]

    def evalFSS2(self, otherSk, revealVal):
        return self.m_CondEval.evaluate(otherSk, revealVal)

    def getFSS2SK(self, c1):
        return self.m_CondEval.getDecryptionKey(c1)

    def onFss1Cmp(self, maskVal):
        ic = ICNew(ring_len=1)
        ret = ic.eval(
            self.id,
            GroupElement(maskVal, FSS_INPUT_LEN),
            self.circuit["fss1"],
        )
        return ret.getValue()

    # AB-Ab-Ba+ab input_calculation & auth_calculation
    def innerProductWithMulOut(self, keys):
        ret = []
        if self.id == 0:
            ret = vec_mul(self.in_wire1, self.in_wire0, SEMI_HONEST_MODULO)
        else:
            ret = [0] * len(self.in_wire0)

        in_s = self.circuit[keys[0]]  # r_a
        in_v = self.circuit[keys[1]]  # r_b
        s_v = self.circuit[keys[2]]  # r_ab

        # -Ba
        ret = vec_sub(
            ret,
            vec_mul(self.in_wire1, in_s, SEMI_HONEST_MODULO),
            SEMI_HONEST_MODULO,
        )
        # -Ab
        ret = vec_sub(
            ret,
            vec_mul(self.in_wire0, in_v, SEMI_HONEST_MODULO),
            SEMI_HONEST_MODULO,
        )
        # +ab
        ret = vec_add(ret, s_v, SEMI_HONEST_MODULO)

        sum = 0
        for v in ret:
            sum = ring_add(sum, v, SEMI_HONEST_MODULO)
        sum = ring_add(sum, self.circuit[keys[3]], SEMI_HONEST_MODULO)
        return sum

    def innerProductWithMul(self, keys):
        ret = []
        if self.id == 0:
            ret = vec_mul(self.in_wire1, self.in_wire0, SEMI_HONEST_MODULO)
        else:
            ret = [0] * len(self.in_wire0)

        in_s = self.circuit[keys[0]]  # r_a
        in_v = self.circuit[keys[1]]  # r_b
        s_v = self.circuit[keys[2]]  # r_ab

        # -Ba
        ret = vec_sub(
            ret,
            vec_mul(self.in_wire1, in_s, SEMI_HONEST_MODULO),
            SEMI_HONEST_MODULO,
        )
        # -Ab
        ret = vec_sub(
            ret,
            vec_mul(self.in_wire0, in_v, SEMI_HONEST_MODULO),
            SEMI_HONEST_MODULO,
        )
        # +ab
        ret = vec_add(ret, s_v, SEMI_HONEST_MODULO)

        sum = 0
        for v in ret:
            sum = ring_add(sum, v, SEMI_HONEST_MODULO)
        #sum = ring_add(sum, self.circuit[keys[3]], SEMI_HONEST_MODULO)
        return sum
    
    def innerProduct(self,s, v):
        _size = len(s)
        ret = 0
        for i in range(_size):
           ret += s[i] * v[i]
        return ret

    
    def modulo_64_bit(self,value):
    # Ensure the value is within the range of a signed 64-bit integer
    # The valid range for signed 64-bit integers is from -2^63 to 2^63 - 1
        MIN_INT_64 = -2**(INPUT_BITS_LEN-1)
        MAX_INT_64 = 2**(INPUT_BITS_LEN-1) - 1

    # Compute the modulo and adjust to always be in the range [0, 2^64)
        mod_value = value % (2**INPUT_BITS_LEN)

    # If the resulting mod value is large enough, it may be negative in adjustment
        if mod_value > MAX_INT_64:
            mod_value -= (2**INPUT_BITS_LEN)
        return mod_value



    def getFirstRoundMessage(self, masked):
        #self.resetInputWires(self.vec_s, self.vec_v)
        #ipRet = self.innerProductWithMulOut(["in_s", "in_v", "s_v", "ip_out"])

        #self.resetInputWires(self.vec_s, self.vec_s)
        #ssRet = self.innerProductWithMulOut(["in_s", "in_s", "s_s", "ss_out"])

        #self.resetInputWires(self.vec_v, self.vec_v)
        #vvRet = self.innerProductWithMulOut(["in_v", "in_v", "v_v", "vv_out"])




        self.resetInputWires(self.vec_s, masked)
        ipRets = self.innerProductWithMul(["in_s", "in_v", "s_v", "ip_out"])

        self.resetInputWires(self.vec_s, self.vec_s)
        ssRets = self.innerProductWithMul(["in_s", "in_s", "s_s", "ss_out"])

        #self.resetInputWires(self.vec_v, self.vec_v)
        #vvRets = self.innerProductWithMul(["in_v", "in_v", "v_v", "vv_out"])

        return[ipRets, ssRets]
        #return[ipRets, ssRets, vvRets]

    def getFirstRoundMessageDrone(self):
        #self.resetInputWires(self.vec_s, self.vec_v)
        #ipRet = self.innerProductWithMulOut(["in_s", "in_v", "s_v", "ip_out"])

        #self.resetInputWires(self.vec_s, self.vec_s)
        #ssRet = self.innerProductWithMulOut(["in_s", "in_s", "s_s", "ss_out"])

        #self.resetInputWires(self.vec_v, self.vec_v)
        #vvRet = self.innerProductWithMulOut(["in_v", "in_v", "v_v", "vv_out"])



        masked_value = vec_add(self.circuit["non_vec_v"], self.circuit["in_v_drone"], SEMI_HONEST_MODULO)
        #print(set(masked_value)==set(self.vec_v))
        self.resetInputWires(self.vec_s, masked_value)
        ipRets = self.innerProductWithMul(["in_s", "in_v", "s_v", "ip_out"])

        self.resetInputWires(self.vec_s, self.vec_s)
        ssRets = self.innerProductWithMul(["in_s", "in_s", "s_s", "ss_out"])

        #self.resetInputWires(self.vec_v, self.vec_v)
        #vvRets = self.innerProductWithMul(["in_v", "in_v", "v_v", "vv_out"])
        #masked_value = vec_add(self.circuit["non_vec_v"], self.circuit["in_v_drone"], SEMI_HONEST_MODULO)
        return[ipRets, ssRets, masked_value]
        #return[ipRets, ssRets, vvRets]

async def async_main(_id,index):
    correctIndexes = []
    TRUE_POSITIVE = 0

    # Create the pool for current server.
    pool = Pool()
    pool.add_http_server(addr=BENCHMARK_IPS[_id], port=BENCHMARK_NETWORK_PORTS[_id])
    pool.add_http_client(
        "server", addr=BENCHMARK_IPS[1 - _id], port=BENCHMARK_NETWORK_PORTS[1 - _id]
    )
    # pool.add_http_client("bank", addr="127.0.0.1", port=NETWORK_BANK_PORT)

    if _id == 0:
        hello = await pool.recv("server")
        await pool.send("server", "Hi, server1")
    else:
        pool.asend("server", "Hi, server0")
        hello = await pool.recv("server")

    all_online_time = 0
    all_online_computation_time = 0
    #for index in range(BENCHMARK_TESTS_AMOUNT):
    server = Server(_id)
        # Step-2: secure computation, Locally load prepared pickle data in setup phase
    parent_location = Path(__file__).resolve().parent.parent

    with open(
            parent_location / ("data/64/offline.pkl" + str(_id) + "-" + str(index)), "rb"
    ) as file:
    share = pickle.load(file)
            #print(share[8])
    server.receiveCircuit(share)

        #start_time = time.time()
        #computation_start_time = time.time()
        #all_comm = 0
        ################# Round-1 #################
        #mShares = server.getFirstRoundMessage()
        #all_online_computation_time += time.time() - computation_start_time
    if _id == 0:
         #   computation_start_time = time.time()
            mShares = server.getFirstRoundMessageDrone()
        #    all_online_computation_time += time.time() - computation_start_time
        #    comm = time.time()
            pool.asend("server", mShares[2])
            otherShares = await pool.recv("server")
         #   all_comm+= time.time() - comm
    else:
         #   comm = time.time()
            #pool.asend("server", mShares)
            masked_value_drone = await pool.recv("server")
            #print(set(masked_value_drone)==set(server.vec_v))
         #   all_comm+= time.time()-comm
         #   computation_start_time = time.time()
            mShares = server.getFirstRoundMessage(masked_value_drone)
         #   all_online_computation_time += time.time() - computation_start_time
         #   comm = time.time()
            pool.asend("server", mShares)
         #   all_comm+= time.time()-comm
        #computation_start_time = time.time()

        #ipWire = ring_add(mShares[0], otherShares[0], SEMI_HONEST_MODULO)
        #ssWire = ring_add(mShares[1], otherShares[1], SEMI_HONEST_MODULO)
        #vvWire = ring_add(mShares[2], otherShares[2], SEMI_HONEST_MODULO)

        #ipWireout = ring_add(mShares[0], otherShares[0], SEMI_HONEST_MODULO)
        #ssWireout = ring_add(mShares[1], otherShares[1], SEMI_HONEST_MODULO)
        #vvWireout = ring_add(mShares[2], otherShares[2], SEMI_HONEST_MODULO)

        ################# Round-1 #################
        #print(ipWireout)
        #print(ssWireout)
        #print(vvWireout)
        ################# Round-2 #################
        #mTruncShare = server.sub_Truncate_Fss(ipWire, ssWire, vvWire)
        #c1 = server.onFss1Cmp(ipWire)
        #sk_Key = bytes(server.getFSS2SK(c1))

        #all_online_computation_time += time.time() - computation_start_time
        #if _id == 0:
        #    pool.asend("server", (mTruncShare, sk_Key))
        #    otherTruncShare, otherSk_Key = await pool.recv("server")
        #else:
        #    pool.asend("server", (mTruncShare, sk_Key))
        #    otherTruncShare, otherSk_Key = await pool.recv("server")
        #computation_start_time = time.time()

        #finalReveal = ring_add(mTruncShare, otherTruncShare, SEMI_HONEST_MODULO)
        #finalReveal = GroupElement(int(finalReveal / TRUNCATE_FACTOR), FSS_INPUT_LEN)

        #output_share = server.evalFSS2(bytearray(otherSk_Key), finalReveal)
        #output_share = output_share.getValue()
        ################# Round-2 #################
        #computation_time = time.time() - computation_start_time
        #online_time = time.time() - start_time
        #all_online_computation_time += time.time() - computation_start_time
        #all_online_computation_time += computation_time
        #all_online_time += time.time() - start_time
        #all_online_time += online_time
        
        #print("Comp.Time:",computation_time)
        #print("Comm.Time:",online_time-computation_time)
        #computation_time = time.time() - computation_start_time
        #all_online_computation_time += computation_time
        #t = time.time() - start_time
    if BENCHMARK_TEST_CORRECTNESS and _id == 0:
            #if _id == 0:
            #    other_output = await pool.recv("server")
            #    await pool.send("server", output_share)
            #else:
            #    await pool.send("server", output_share)
            #    other_output = await pool.recv("server")

            #final_output = ring_add(output_share, other_output, 2)
            computation_start_time = time.time()
            ipWireout = ring_add(mShares[0], otherShares[0], SEMI_HONEST_MODULO)
            ssWireout = ring_add(mShares[1], otherShares[1], SEMI_HONEST_MODULO)

            left = server.modulo_64_bit(ipWireout)
            c1 = left >= 0
            #print("c1: ", index, c1)
            #print(left)
            left = left * left
            left = left * (1 / THRESHOLD_TAU_SQUARE)
            #print("leftwithtau:", left)
            right = server.modulo_64_bit(ssWireout)
            v = server.circuit["non_vec_v"]#server.modulo_64_bit(vvWireout)
            
            vv = server.innerProduct(v,v)
            #print(right)
            #print(v)
            right = right * vv
            # print("right-track: ",right)
            c2 = left - right >= 0
            #print("leftwithtau:", left)
            #print("c1: ", index, c1)
            #print("c2: ", index, c2, "\n")

            c = c1 and c2
            #computation_time = time.time() - computation_start_time
            #online_time = time.time() - start_time
            #all_online_computation_time += time.time() - computation_start_time
            #all_online_computation_time += computation_time
            #all_online_time += time.time() - start_time
            #all_online_time += online_time
            #print("Comp.Time:",online_time - all_comm)
            #print("Comm.Time:",all_comm)
            #print("Online Time:",online_time)
            #print("Communication:",all_comm)
            #if _id == 0:
            if ALL_RESULTS[index] == c:
             #       print(f"By {index} success.")
                    TRUE_POSITIVE+=1
                    correctIndexes.append(index)
            #        print("Total true positives are ", TRUE_POSITIVE)
                    # print("SAMPLE_NUM is: ",BENCHMARK_TESTS_AMOUNT)
           #         print("TP is ", TRUE_POSITIVE / BENCHMARK_TESTS_AMOUNT)

            else:
                    print(f"By {index} mismatch.")
    elif BENCHMARK_TEST_CORRECTNESS and _id == 1:
            #computation_time = time.time() - computation_start_time
          #  online_time = t
            #all_online_computation_time += time.time() - computation_start_time
            #all_online_computation_time += computation_time
            #all_online_time += time.time() - start_time
         #   all_online_time += online_time
         #   print("Comp.Time:",all_online_computation_time)
        #    print("Comm.Time:",all_comm)
       #     print("Online Time:",online_time)
      #      print("Communication:",all_comm)

     #   print("TP is ", TRUE_POSITIVE / BENCHMARK_TESTS_AMOUNT)
        ################ Return partial values and MAC codes ######
        # await pool.send("bank", [maskEval_shares,partialMac] )
        ################ Return partial values and MAC codes ######
    #if _id == 1  or _id == 0:
      #  print(
      #      "Compuation time cost is: ",
      #      all_online_computation_time / BENCHMARK_TESTS_AMOUNT,
      #  )
      #  print(
      #      "Commu. time cost is: ",
      #      (all_online_time - all_online_computation_time) / BENCHMARK_TESTS_AMOUNT,
      #  )

    if _id == 0:
        await pool.send("server", "Let's close!")
        other = await pool.recv("server")
    else:
        other = await pool.recv("server")
        await pool.send("server", "Let's close!")

    await pool.shutdown()


if __name__ == "__main__":
    _id = int(sys.argv[1])
    index = int(sys.argv[2])
    loop = asyncio.get_event_loop()
    loop.run_until_complete(async_main(_id,index))
	

