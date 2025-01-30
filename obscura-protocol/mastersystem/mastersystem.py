"""
The main testing script that connects to the client and server, runs the tests and collects data
"""
import datetime
import os
import condeval
import configparser
import time
import math
import json
#from porto_data_handler.visualise import show_on_map, print_colliding_coords, print_trajectory, print_trajectory_to_file, print_colliding_to_file
#from trajectory_matching.setup import get_n_values, run_client_trajectory_matching
# collision threshold constant
from pyproj import Proj
from itertools import pairwise, chain
import pandas as pd
import numpy as np
from Crypto.Util import number

sec_lvl = None
mt_alg = None


"""Parse config file"""
config = configparser.ConfigParser()
config.read('config.ini')

def gen_safe_prime(BITS):
    qq = 1
    while not number.isPrime(qq):
        pp = number.getPrime(BITS - 1)
        qq = 2 * pp + 1
    return qq



# override config if parameters already provided
def orverride_config(sec_lvl, mt_alg):
        config.set('misc', 'security_level', str(sec_lvl))
        config.set('misc', 'mt_algorithm', str(mt_alg))

client_ip = config.get('client', 'ip_address')
client_username = config.get('client', 'username')
client_password = config.get('client', 'password')
#client_key = config.get('client', 'private_ssh_key_path')
client_exec_path = config.get('client', 'executable_path')
client_exec_name = config.get('client', 'executable_name')
client_pffrocd_path = config.get('client', 'pffrocd_path')

server_ip = config.get('server', 'ip_address')
server_username = config.get('server', 'username')
server_password = config.get('server', 'password')
#server_key = config.get('server', 'private_ssh_key_path')
server_exec_path = config.get('server', 'executable_path')
server_exec_name = config.get('server', 'executable_name')
server_pffrocd_path = config.get('server', 'pffrocd_path')

#nr_of_people = config.getint('misc', 'nr_of_people')
niceness = config.getint('misc', 'niceness')
#starting_person = config.getint('misc', 'starting_person')
#bit_length = config.getint('misc', 'bit_length')
gather_energy_data = config.getboolean('misc', 'gather_energy_data')

# if bit_length == 64:
#     NUMPY_DTYPE = np.float64
# elif bit_length == 32:
#     NUMPY_DTYPE = np.float32
# elif bit_length == 16:
#     NUMPY_DTYPE = np.float16
# else:
#     raise Exception("Invalid bit length")

# client_exec_name += f"_{bit_length}"
# server_exec_name += f"_{bit_length}"



def run_test():

    file_path_csv = "../../data/new_emb1.txt"
    #sample_size = 4000
    # load trajectory data
    #print(f"Loading {file_path_csv} ...")
    #df = trajectory_data.load(
    #    file_path=file_path_csv,
    #    trip_id_col="PAIR_ID",
    #    space_and_time_col="CLIENT"
    #)
    #df = df.head(sample_size)
    #ids_client = df.index.values
    #trajectory_samples_gps_client = df["CLIENT"].to_numpy()
    #trajectory_samples_client = gps_to_cart(trajectory_samples_gps_client)
    
    #print(gps_to_cart(trajectory_samples_gps_client))
    #print(gps_to_cartv2(trajectory_samples_gps_client))


    #df = trajectory_data.load(
    #    file_path=file_path_csv,
    #    trip_id_col="PAIR_ID",
    #    space_and_time_col="SERVER"
    #)
    #df = df.head(sample_size)
    #ids_server = df.index.values
    #trajectory_samples_gps_server = df["SERVER"].to_numpy()
    #trajectory_samples_server = gps_to_cart(trajectory_samples_gps_server)
    
    index = 0
    #size_trajectories_server = len(trajectory_samples_server[0])
    #size_trajectories_client = len(trajectory_samples_client[0])
    #trajectory_samples_server = trajectory_samples_server[0]
    #trajectory_samples_client = trajectory_samples_client[0]
    #df_client_list=[]
    #df_server_list= []
    #df_c = pd.DataFrame()
    #df_s = pd.DataFrame()
    #df_server_out = pd.DataFrame()
    #df_client_out = pd.DataFrame()
    #print("Generating safe primes p and q ...")
    #p_client = gen_safe_prime(512)
    #q_client = gen_safe_prime(512)
    #p_server = gen_safe_prime(512)
    #q_server = gen_safe_prime(512)
    #print(p_client)
    #print(q_client)
    print("Finishe generating")
    ###run time test###
    server_sfe_output = ''
    server_sfe_error = ''
    client_sfe_output = ''
    client_sfe_error = ''
    execution = False
    if execution:
        command2 = f"python3 {client_exec_path}/server.py 1"
        command1 = f"python3 {server_exec_path}/server.py 0"
        print(command1)
        print(command2)
        output = condeval.execute_command_parallel_alternative([server_ip, client_ip], server_username, client_username, server_password, client_password, command1, command2, timeout=30)
        for host_output in output:
            hostname = host_output.host
            stdout = list(host_output.stdout)
            stderr = list(host_output.stderr)
        #logger.debug("Host %s: exit code %s, output %s, error %s" % (
#        hostname, host_output.exit_code, stdout, stderr))
            if hostname == server_ip:
                server_sfe_output = '\n'.join(stdout)
                server_sfe_error = '\n'.join(stderr)
            if hostname == client_ip:
                client_sfe_output = '\n'.join(stdout)
                client_sfe_error = '\n'.join(stderr)
        print(server_sfe_output)
        print(client_sfe_output)
        print(server_sfe_error)
        print(client_sfe_error)
        f = open("client_leak_energy_nuc.txt", "a")
        f.write(client_sfe_output)
        f.close()
        f = open("server_leak_energy_nuc.txt", "a")
        f.write(server_sfe_output)
        f.close()


 #   while index < size_trajectories_client  and index < size_trajectories_server:
    
    for x in range(0,1000):
        correct = True
        while(correct):
                # generate safe primes

           current_datetime = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
  #          trajectory_server = trajectory_samples_server[index]
  #      
  #          trajectory_client = trajectory_samples_client[index]
  #          id_server = ids_server[index] 
  #          id_client = ids_client[index]
           logger = condeval.setup_logging(current_datetime)
            # stdout1, stderr1, stdout2, stderr2 = pffrocd.execute_command_parallel(host1=client_ip, username1=client_username, command1=f"{client_exec_path}/{client_exec_name} -r 1 -a {server_ip} -f {client_exec_path}/embeddings.txt", host2=server_ip, username2=server_username, command2=f"{server_exec_path}/{server_exec_name} -r 0 -a {server_ip} -f {server_exec_path}/embeddings.txt", private_key_path1=client_key, private_key_path2=server_key)
            # logger.debug("sfe done")
            # logger.debug(f"{stdout1=}")
            # logger.debug(f"{stderr1=}")
            # logger.debug(f"{stdout2=}")
            # logger.debug(f"{stderr2=}")

           command1 = f"cd {server_exec_path} && echo {server_password} | sudo -S nice -n {niceness} /usr/bin/time -v python3.9 {server_exec_name} 0 {x}"
           command2 = f"cd {client_exec_path} && echo {client_password} | sudo -S nice -n {niceness} /usr/bin/time -v python3.9 {client_exec_name} 1 {x}"
           command11 = f"cd {server_exec_path} ; nice -n {niceness} /usr/bin/time -v python3.9 {server_exec_name} 0 {x}"
           command22 = f"cd {client_exec_path} ; nice -n {niceness} /usr/bin/time -v python3.9 {client_exec_name} 1 {x}"
           
           #print(command1)
           #command1 = f"cd {server_exec_path} ; ls -la"
            #command2 = f"cd {client_exec_path}/data ; ls -la"
           sfe_start_time  = time.time()
           #output = condeval.execute_command_parallel_alternative([server_ip,client_ip], server_username, client_username, server_password, client_password, command1, command2, timeout=120)
           output = condeval.execute_command_parallel_alternative_v2([server_ip, client_ip],[server_username, client_username],[server_password, client_password], [command11, command22])
           #output = condeval.execute_command_parallel_alternative([client_ip, server_ip], client_username, server_username, client_password, server_password, command2, command1, timeout=30)
           print(output[0])
           print(output[1])

           sfe_time = time.time() - sfe_start_time
           print(output)
           logger.info(f"Finished! Total sfe time: {sfe_time} ")
           server_sfe_output = ''
           server_sfe_error = ''
           client_sfe_output = ''
           client_sfe_error = ''
  #         print(output)
        #    for host_output in output:
        #         hostname = host_output.host
        #         stdout = list(host_output.stdout)
        #         stderr = list(host_output.stderr)
        #         logger.debug("Host %s: exit code %s, output %s, error %s" % (
        #         hostname, host_output.exit_code, stdout, stderr))
        #         if hostname == server_ip:
        #             server_sfe_output = ''.join(stdout)
        #             server_sfe_error = ''.join(stderr)
        #         if hostname == client_ip:
        #             client_sfe_output = ''.join(stdout)
        #             client_sfe_error = ''.join(stderr)
        #    print(server_sfe_output)
        #    print(client_sfe_output)
           server_ram_usage = condeval.parse_usr_bin_time_output(output[0])
           client_ram_usage = condeval.parse_usr_bin_time_output(output[1])
           if server_ram_usage is None or client_ram_usage is None:
               break
           logger.debug(f"{x},server, Parsed server ram usage: {server_ram_usage.get('Maximum resident set size (kbytes)')}")
           logger.debug(f"{x},client, Parsed client ram usage: {client_ram_usage.get('Maximum resident set size (kbytes)')}")
#
#            # # rerun the routine with powertop to gather energy consumption data
           if gather_energy_data and client_ram_usage.get('User time (seconds)') is not None and server_ram_usage.get('User time (seconds)') is not None:
    #            logger.info("Running powertop to gather energy consumption data...")
                running_time_client = float(client_ram_usage['User time (seconds)'])
                running_time_server = float(server_ram_usage['User time (seconds)'])
                powertop_command = f"sudo /usr/sbin/powertop --csv=log/powertop_leak_nuc_{current_datetime}.csv -t {sfe_time + 1}"
                powertop_command_server = f"sudo /usr/sbin/powertop --csv=log/powertop_leak_nuc_{current_datetime}.csv -t {sfe_time + 1}"
                #output = condeval.execute_command_parallel_alternative_v3([server_ip, client_ip], [server_username, client_username], [server_password, client_password], [f"{command1} & {powertop_command_server}", f"{command2} & {powertop_command}"], timeout=300)
                output = condeval.execute_command_parallel_alternative_v3([client_ip, server_ip], [client_username, server_username], [client_password, server_password], [f"{command22} & {powertop_command}", f"{command11} & {powertop_command_server}"], timeout=300)
                print(output[0])
                print(output[1])
                logger.debug(f"client all values : {output[0]}")
                logger.debug(f"server all values : {output[1]}")
                # get the powertop files from hosts and parse them and save in the dataframe
                # for host_output in output:
                #     hostname = host_output.host
                #     stdout = list(host_output.stdout)
                #     stderr = list(host_output.stderr)
                #     logger.debug("Host %s: exit code %s, output %s, error %s" % (
                #     hostname, host_output.exit_code, stdout, stderr))
                #     if hostname == server_ip:
                #         server_sfe_output = ''.join(stdout)
                #         server_sfe_error = ''.join(stderr)
                #     if hostname == client_ip:
                #         client_sfe_output = ''.join(stdout)
                #         client_sfe_error = ''.join(stderr)
                all_values, energy_client = condeval.get_energy_consumption(client_ip, client_username, client_password, f"{client_exec_path}/log/powertop_leak_nuc_{current_datetime}.csv", f"{client_pffrocd_path}/clientnuc/powertop_leak_nuc_{current_datetime}.csv",running_time_client + 1)
                logger.debug(f"All values from powertop for client: {all_values}")
                logger.debug(f"Energy client: {energy_client}")
                all_values, energy_server = condeval.get_energy_consumption(server_ip, server_username, server_password, f"{server_exec_path}/log/powertop_leak_nuc_{current_datetime}.csv", f"{server_pffrocd_path}/servernuc/powertop_leak_nuc_{current_datetime}.csv", running_time_server + 1)
                logger.debug(f"All values from powertop for server: {all_values}")
                logger.debug(f"Energy server: {energy_server}")
                correct = False
           else:
                correct = True
                energy_client = 'not measured'
                energy_server = 'not measured'
                if gather_energy_data is False:
                    correct = False

    #        index+=1
            # # save all results and timing data
                #server_parsed_sfe_output = condeval.parse_aby_output(server_sfe_output)
                #client_parsed_sfe_output = condeval.parse_aby_output(client_sfe_output)
            #if not server_parsed_sfe_output or not client_parsed_sfe_output:
            #     continue
            # if not server_ram_usage or not client_ram_usage:
            #     continue
            # logger.info(f"Server throughput (for this run, reported by ABY): {float(server_parsed_sfe_output['hardware.throughput']) * 8:.2f} Mbits/sec")
            # logger.info(f"Client throughput (for this run, reported by ABY): {float(client_parsed_sfe_output['hardware.throughput']) * 8:.2f} Mbits/sec")
            # logger.info(f"Server total time: {float(server_parsed_sfe_output['timings.total']) / 1000}")
            # logger.info(f"Client total time: {float(client_parsed_sfe_output['timings.total']) / 1000}")
            # cos_dist_sfe = float(server_parsed_sfe_output['cos_dist_sfe'])
            # result = cos_dist_sfe < pffrocd.threshold
            # expected_result = ref_img.split('/')[1] == img.split('/')[1] # check if the images belong to the same person
            # cos_dist_np = pffrocd.get_cos_dist_numpy(ref_img_embedding, img_embedding)
            # server_list_of_sfe_values = list(server_parsed_sfe_output.values())
            # client_list_of_sfe_values = list(client_parsed_sfe_output.values())
            # logger.debug(f"{server_parsed_sfe_output=}")
            # logger.debug(f"{server_list_of_sfe_values=}")
            # logger.debug(f"{client_parsed_sfe_output=}")
            # logger.debug(f"{client_list_of_sfe_values=}")
            # # if ram_usage asked for password for sudo delete that entry
            # logger.debug(f"Checking if the key <[sudo] password for {server_username}> exists")
            # server_ram_usage.pop(f'[sudo] password for {server_username}', None)
            # client_ram_usage.pop(f'[sudo] password for {client_username}', None)
            # server_list_of_ram_values = list(server_ram_usage.values()) # [1:] # remove the first element, asking for sudo
            # client_list_of_ram_values = list(client_ram_usage.values())
            # logger.debug(f"{server_ram_usage=}")
            # logger.debug(f"{client_ram_usage=}")
            # logger.debug(f"{server_list_of_ram_values=}")
            # logger.debug(f"{client_list_of_ram_values=}")
            # to_be_appended = [ref_img, img, result, expected_result, cos_dist_np, cos_dist_sfe, sfe_time + extraction_time, sfe_time, extraction_time] + server_list_of_ram_values + client_list_of_ram_values +  [energy_client, energy_server] + server_list_of_sfe_values + client_list_of_sfe_values
            # logger.debug(f"{to_be_appended=}")
            # logger.debug(f"{pffrocd.columns=}")
            # # make and iteratively save the dataframe with results        
            # df = pd.DataFrame([to_be_appended], columns=pffrocd.columns)
            # output_path = f"dfs/{current_datetime}.csv"
            # # append dataframe to file, only write headers if file does not exist yet
            # df.to_csv(output_path, mode='a', header=not os.path.exists(output_path))


if __name__ == "__main__":
    run_test()
