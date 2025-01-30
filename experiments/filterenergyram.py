import os
import pandas as pd
import json
import math
import re
def parse_usr_bin_time_output(output):
    """Parses the benchmark output of usr/bin/time and returns stats of interest in a dictionary"""
    metrics = {}
    lines = output.strip().split(',')

    for line in lines:
        #try:
            if "DEBUG" in line:
                key = "ID"
                value = line.split('-')[2].strip()
                print(value.find("client all values"))
                if value.find("client all values") == -1 and value.find("server all values") == -1:
                    metrics[key] = int(value)
            if 'Command being timed' in line:
                key = "Index"
                print(line.split(' '))
                value = line.split(' ')[7].strip()
                metrics[key] = int(''.join(re.findall(r'\d', value)))
            if 'Maximum resident set size (kbytes)' in line:
                key = "ram"
                print(line.split(":"))
                value = line.split(":")[1].strip(" '")
                metrics[key] = int(value)
            if 'User time (seconds)' in line:
                key = "runtime"
                print(line.split(":"))
                value = line.split(":")[1].strip(" '")
                metrics[key] = float(value)

        #except:
        #    return None
               
    return metrics

def extract_ram_energy(directory_in_str, limit, watt):
    #filepath = os.path.join("../log", filename)
    directory = os.fsencode(directory_in_str)
    print(directory)
    ptop_client=[]
    energy_client=[]
    ram_client=[]
    run_client = []
    ptop_server=[]
    energy_server=[]
    ram_server=[]
    run_server=[]
    id_client=[]
    id_server=[]
    index_client=[]
    index_server=[]
    f_filename = []
    #ids =[1273, 1939, 2400, 2674, 2752, 3692, 4450, 4733]
    counter = 0 
    alreadynot=False

    for file in os.listdir(directory):
        filename = os.fsdecode(file)
        print(filename)
        if filename.endswith(".log"): 
            counter += 1
            directory = os.fsdecode(directory)
            print(os.path.join(directory, filename))
            print(f"--- File: {directory+'/'+filename} ---")
            alreadynotclient=False
            alreadynotserver=False
            ramclient= False
            energyclient=False
            powertopclient=False
            ramserver= False
            energyserver=False
            powertopserver=False
            with open(directory+"/"+filename, 'r') as file:
                lines = file.readlines()
                total_lines = len(lines)
                print(f"Total number of lines: {total_lines}")
                
                for i, line in enumerate(lines):
                    if "Parsed client ram usage" in line:
                        metrics = parse_usr_bin_time_output(line)
                        print(type(metrics))
                        #if metrics.get('ID') not in id_client and  metrics.get('ID') not in ids:
                        id_client.append(metrics.get('ID'))
                        
                    if "client all values" in line:
                        index_client.append(metrics.get('Index'))
                        ram_client.append(metrics.get('ram'))
                        run_client.append(metrics.get('runtime'))
                        alreadynotclient = True
                        ramclient=True

                    
                    if "Parsed server ram usage" in line:
                        metrics = parse_usr_bin_time_output(line)
                        print(metrics)
                        #if metrics.get('ID') not in id_server and  metrics.get('ID') not in ids:
                        id_server.append(metrics.get('ID'))

                    if "server all values" in line:
                        index_server.append(metrics.get('Index'))
                        ram_server.append(metrics.get('ram'))
                        run_server.append(metrics.get('runtime'))
                        alreadynotserver = True
                        ramserver=True
                    
                    if "Energy client:" in line and alreadynotclient:
                        energy_client.append(float(line.split(":")[3]))
                        print(float(line.split(":")[3]))
                        energyclient=True
                        #counter +=1

                    
                    if "Energy server:" in line and alreadynotserver:
                        energy_server.append(float(line.split(":")[3]))
                        energyserver=True
                    #else: f_filename.append(filename)
                    if "from powertop for client:" in line and alreadynotclient:
                        print(line.split(":"))
                        print(line.split(":")[3].split(" "))
                        split = line.split(":")[3].split(" ")
                        if split[5] != '' and  (split[5] != 'W' or split[5] != 'mW'):
                            value = float(split[5])
                            unit = split[6]
                            if unit == 'mW':
                                value*=0.001
                            elif unit == 'uW':
                                value*=0.000001
                            elif unit == 'W':
                                pass

                            ptop_client.append(value)
                        elif split[6] != '' and  (split[6] != 'W' or split[6] != 'mW'):
                            value = float(split[6])
                            unit = split[7]
                            if unit == 'mW':
                                value*=0.001
                            elif unit == 'uW':
                                value*=0.000001
                            elif unit == 'W':
                                pass
                            ptop_client.append(value)
                        elif  split[7] != '' and  (split[7] != 'W' or split[7] != 'mW'):
                            value = float(split[7])
                            unit = split[8]
                            if unit == 'mW':
                                value*=0.001
                            elif unit == 'uW':
                                value*=0.000001
                            elif unit == 'W':
                                pass
                            ptop_client.append(value)
                        elif  split[8] != '' and  (split[8] != 'W' or split[8] != 'mW'):
                            value = float(split[8])
                            unit = split[9]
                            if unit == 'mW':
                                value*=0.001
                            elif unit == 'uW':
                                value*=0.000001
                            elif unit == 'W':
                                pass
                            ptop_client.append(value)
                        else:
                            print(line)
                        #counter+=1
                        powertopclient=True
                    if "from powertop for server:" in line and alreadynotserver:
                        split = line.split(":")[3].split(" ")
                        if split[5] != '' and  (split[5] != 'W' or split[5] != 'mW'):
                            value = float(split[5])
                            unit = split[6]
                            if unit == 'mW':
                                value*=0.001
                            elif unit == 'uW':
                                value*=0.000001
                            elif unit == 'W':
                                pass

                            ptop_server.append(value)
                        elif split[6] != '' and  (split[6] != 'W' or split[6] != 'mW'):
                            value = float(split[6])
                            unit = split[7]
                            if unit == 'mW':
                                value*=0.001
                            elif unit == 'uW':
                                value*=0.000001
                            elif unit == 'W':
                                pass
                            ptop_server.append(value)
                        elif  split[7] != '' and  (split[7] != 'W' or split[7] != 'mW'):
                            value = float(split[7])
                            unit = split[8]
                            if unit == 'mW':
                                value*=0.001
                            elif unit == 'uW':
                                value*=0.000001
                            elif unit == 'W':
                                pass
                            ptop_server.append(value)
                        elif  split[8] != '' and  (split[8] != 'W' or split[8] != 'mW'):
                            value = float(split[8])
                            unit = split[9]
                            if unit == 'mW':
                                value*=0.001
                            elif unit == 'uW':
                                value*=0.000001
                            elif unit == 'W':
                                pass
                            ptop_server.append(value)
                        else:
                            print(line)

                        powertopserver=True
                                   #print(line.rstrip())  # rstrip() to remove newline characters
                        if i + 1 >= limit:
                            break
                        print()

                    #else: f_filename.append(filename)

             
                if(powertopclient and energyclient and ramclient) or (powertopserver and energyserver and ramserver):
                    print("allvalues")
                else:
                    print("filename:",filename)
                    f_filename.append(filename)
    f_filename = set(f_filename)
    print(counter) 
    print(len(set(index_client)))  
    print(len(set(id_client)))  
    
    arr_client = {'ix': index_client, 'id': id_client,'ram':ram_client, 'energy': energy_client, 'watt': ptop_client, 'runtime': run_client}

    print(arr_client)
    df_client= pd.DataFrame(arr_client)
    df_client.set_index('ix', inplace=True)
    df_client.sort_index(inplace=True)
    print(df_client)
    
    arr_server = {'ix': index_server, 'id': id_server,'ram':ram_server, 'energy': energy_server, 'watt': ptop_server, 'runtime': run_server}
    df_server= pd.DataFrame(arr_server)
    df_server.set_index('ix', inplace=True)
    df_server.sort_index(inplace=True)
    print(df_server)
    return df_client,df_server


def extract_ram_energy_without_watt(directory_in_str, limit, watt):
    #filepath = os.path.join("../log", filename)
    directory = os.fsencode(directory_in_str)
    #print(directory)
    ptop_client=[]
    energy_client=[]
    ram_client=[]
    run_client = []
    ptop_server=[]
    energy_server=[]
    ram_server=[]
    run_server=[]
    id_client=[]
    id_server=[]
    index_client=[]
    index_server=[]
    f_filename = []
    #ids =[1273, 1939, 2400, 2674, 2752, 3692, 4450, 4733]
    counter = 0 
    alreadynot=False

    for file in os.listdir(directory):
        filename = os.fsdecode(file)
        #print(filename)
        if filename.endswith(".log"): 
            counter += 1
            directory = os.fsdecode(directory)
            #print(os.path.join(directory, filename))
            #print(f"--- File: {directory+'/'+filename} ---")
            alreadynotclient=False
            alreadynotserver=False
            ramclient= False
            energyclient=False
            powertopclient=False
            ramserver= False
            energyserver=False
            powertopserver=False
            with open(directory+"/"+filename, 'r') as file:
                lines = file.readlines()
                total_lines = len(lines)
                #print(f"Total number of lines: {total_lines}")
                
                for i, line in enumerate(lines):
                    if "Parsed client ram usage" in line:
                        metrics = parse_usr_bin_time_output(line)
                        #print(type(metrics))
                    
                    if "client all values" in line:
                        metrics = parse_usr_bin_time_output(line)
                        index_client.append(metrics.get('Index'))
                        ram_client.append(metrics.get('ram'))
                        run_client.append(metrics.get('runtime'))
                        alreadynotclient = True
                        ramclient=True

                    
                    if "Parsed server ram usage" in line:
                        metrics = parse_usr_bin_time_output(line)
                        #print(metrics)
                    if "server all values" in line:
                        metrics = parse_usr_bin_time_output(line)
                        index_server.append(metrics.get('Index'))
                        ram_server.append(metrics.get('ram'))
                        run_server.append(metrics.get('runtime'))
                        alreadynotserver = True
                        ramserver=True

                    
                    if "Energy client:" in line and alreadynotclient:
                        energy_client.append(float(line.split(":")[3]))
                        #print(float(line.split(":")[3]))
                        energyclient=True
                        #counter +=1

                    
                    if "Energy server:" in line and alreadynotserver:
                        energy_server.append(float(line.split(":")[3]))
                        energyserver=True
                    #else: f_filename.append(filename)
                    if "from powertop for client:" in line and alreadynotclient:
                        #print(line.split(":"))
                        #print(line.split(":")[3].split(" "))
                        split = line.split(":")[3].split(" ")
                        if split[5] != '' and  (split[5] != 'W' or split[5] != 'mW'):
                            value = float(split[5])
                            unit = split[6]
                            if unit == 'mW':
                                value*=0.001
                            elif unit == 'uW':
                                value*=0.000001
                            elif unit == 'W':
                                pass

                            ptop_client.append(value)
                        elif split[6] != '' and  (split[6] != 'W' or split[6] != 'mW'):
                            value = float(split[6])
                            unit = split[7]
                            if unit == 'mW':
                                value*=0.001
                            elif unit == 'uW':
                                value*=0.000001
                            elif unit == 'W':
                                pass
                            ptop_client.append(value)
                        elif  split[7] != '' and  (split[7] != 'W' or split[7] != 'mW'):
                            value = float(split[7])
                            unit = split[8]
                            if unit == 'mW':
                                value*=0.001
                            elif unit == 'uW':
                                value*=0.000001
                            elif unit == 'W':
                                pass
                            ptop_client.append(value)
                        elif  split[8] != '' and  (split[8] != 'W' or split[8] != 'mW'):
                            value = float(split[8])
                            unit = split[9]
                            if unit == 'mW':
                                value*=0.001
                            elif unit == 'uW':
                                value*=0.000001
                            elif unit == 'W':
                                pass
                            ptop_client.append(value)
                        else:
                            print("Missed")
                            print(line)
                            print(lines)
                        #counter+=1
                        powertopclient=True
                    if "from powertop for server:" in line and alreadynotserver:
                        split = line.split(":")[3].split(" ")
                        if split[5] != '' and  (split[5] != 'W' or split[5] != 'mW'):
                            value = float(split[5])
                            unit = split[6]
                            if unit == 'mW':
                                value*=0.001
                            elif unit == 'uW':
                                value*=0.000001
                            elif unit == 'W':
                                pass

                            ptop_server.append(value)
                        elif split[6] != '' and  (split[6] != 'W' or split[6] != 'mW'):
                            value = float(split[6])
                            unit = split[7]
                            if unit == 'mW':
                                value*=0.001
                            elif unit == 'uW':
                                value*=0.000001
                            elif unit == 'W':
                                pass
                            ptop_server.append(value)
                        elif  split[7] != '' and  (split[7] != 'W' or split[7] != 'mW'):
                            value = float(split[7])
                            unit = split[8]
                            if unit == 'mW':
                                value*=0.001
                            elif unit == 'uW':
                                value*=0.000001
                            elif unit == 'W':
                                pass
                            ptop_server.append(value)
                        elif  split[8] != '' and  (split[8] != 'W' or split[8] != 'mW'):
                            value = float(split[8])
                            unit = split[9]
                            if unit == 'mW':
                                value*=0.001
                            elif unit == 'uW':
                                value*=0.000001
                            elif unit == 'W':
                                pass
                            ptop_server.append(value)
                        else:
                            print(line)

                        powertopserver=True
                                   #print(line.rstrip())  # rstrip() to remove newline characters
                        if i + 1 >= limit:
                            break
                        print()

                    #else: f_filename.append(filename)

             
                if(powertopclient and energyclient and ramclient) or (powertopserver and energyserver and ramserver):
                    print("allvalues")
                else:
                    print("filename:",filename)
                    f_filename.append(filename)
    f_filename = set(f_filename)
    print(counter) 
    print(len(set(index_client)))  
    print(len(set(id_client)))
    print(len(ptop_client))
    print(len(ptop_server))
 
    arr_client = {'ix': index_client, 'id': index_client,'ram':ram_client, 'energy': energy_client, 'watt': ptop_client, 'runtime': run_client}
    
    #print(arr_client)
    df_client= pd.DataFrame(arr_client)
    df_client.set_index('ix', inplace=True)
    df_client.sort_index(inplace=True)
    #print(df_client)
    arr_server = {'ix': index_server, 'id': index_server,'ram':ram_server, 'energy': energy_server,  'watt': ptop_server, 'runtime': run_server}
    df_server= pd.DataFrame(arr_server)
    df_server.set_index('ix', inplace=True)
    df_server.sort_index(inplace=True)
    #print(df_server)
    return df_client,df_server

def retrievedataenergy(df,df_energy):
    initiator_client_space_full_df = {}
    responder_client_space_full_df = {}
    initiator_client_energy_full_df = {}
    responder_client_energy_full_df = {}
    ids =[1273, 1939, 2400, 2674, 2752, 3692, 4450, 4733]
    if len(df) ==3229:
        length = len(df)-1
    else:
        length = len(df)
    for i in range(0,length):
    
        temp = json.loads(df["performance"][i])
        id = df["ID"][i]
        if id not in ids and temp["1"]["role"]== "initiator" and id == df_energy['id'][i]:
            initiator_client_space_full_df[df["ID"][i]] = temp
            initiator_client_energy_full_df[id] = {}
            #initiator_client_energy_full_df[id]["powertop"] = df_energy["powertop"].iloc[i]
            initiator_client_energy_full_df[id]["ram"] = df_energy["ram"].iloc[i]
            initiator_client_energy_full_df[id]["energy"] = df_energy["energy"].iloc[i]
            
        
        if id not in ids and temp["1"]["role"]== "responder" and id == df_energy['id'][i]:
        
            responder_client_space_full_df[df["ID"][i]] = temp
            responder_client_energy_full_df[id] = {}
            #responder_client_energy_full_df[id]["powertop"] = df_energy["powertop"].iloc[i]
            responder_client_energy_full_df[id]["ram"] = df_energy["ram"].iloc[i]
            responder_client_energy_full_df[id]["energy"] = df_energy["energy"].iloc[i]


    #iterate_nested_json_for_loop(temp)

    ls_in = []
    index=0
    for key, value in initiator_client_space_full_df.items():
        initiator ={}   
        counter = 0
        sum_time = 0
        sum_bandwidth = 0 
        initiator["ID"]=key
        for round, values in value.items():
        #print(round)
            sum_time += values["time"]
            sum_bandwidth += values["bandwidth_response"]        
            counter+=1
        
        initiator["time_space"] = sum_time 
        initiator["bandwidth_space"] = sum_bandwidth 
        initiator["round"] = counter+1
        initiator["domain"] = "space" 
        #initiator["powertop"] = initiator_client_energy_full_df[key]["powertop"]
        initiator["ram"] = initiator_client_energy_full_df[key]["ram"]
        initiator["energy"] = initiator_client_energy_full_df[key]["energy"]

        ls_in.append(initiator)
        index+=1

 
    ls_res = []
    index = 0
    for key, value in responder_client_space_full_df.items():
    #print(key,value)
        responder ={}  
        counter = 0
        sum_time = 0
        sum_bandwidth = 0 
        responder["ID"]=key
        for round, values in value.items():
        #print(round)
            sum_time += values["time"]
            sum_bandwidth += values["bandwidth"]        
            counter+=1
        
        responder["time_space"] = sum_time 
        responder["bandwidth_space"] = sum_bandwidth
        responder["round"] = counter 
        responder["domain"] = "space"
        #responder["powertop"] = responder_client_energy_full_df[key]["powertop"]
        responder["ram"] = responder_client_energy_full_df[key]["ram"]
        responder["energy"] = responder_client_energy_full_df[key]["energy"]
        ls_res.append(responder)
        index+=1

#print(initiator)


#iterate_nested_json_for_loop(json.loads(df['performance'][1]))
#print(json.loads(df['performance'][1]))
    #print(responder)

    df_initiator_client = pd.json_normalize(ls_in)
    df_responder_client = pd.json_normalize(ls_res)
    print(df_initiator_client)
    print(df_responder_client)
    return df_initiator_client, df_responder_client


#N = 30  # Number of lines to print from each file
#for filename in filenames:
#    print_file_info(filename)
#extract_ram_energy('MeasurementPC/energyram/full')


def retrievedataenergynoncorpi(df,df_energy):
    initiator_client_space_full_df = {}
    responder_client_space_full_df = {}
    initiator_client_energy_full_df = {}
    responder_client_energy_full_df = {}
    ids =[1273, 1939, 2400, 2674, 2752, 3692, 4450, 4733, 4546, 3675]
    if len(df) ==3229:
        length = len(df)-1
    else:
        length = len(df)
    j=0
    for index, energy in df_energy.iterrows():
        
        for i in range(0,length):
        
            temp = json.loads(df["performance"][i])
            id = df["ID"][i]
            if id not in ids and temp["1"]["role"]== "initiator" and id == energy['id']:
                initiator_client_space_full_df[df["ID"][i]] = temp
                initiator_client_energy_full_df[id] = {}
            #initiator_client_energy_full_df[id]["powertop"] = df_energy["powertop"].iloc[i]
                initiator_client_energy_full_df[id]["ram"] = energy["ram"]
                if math.isnan(float(energy["watt"]*energy["runtime"])):
                    initiator_client_energy_full_df[id]["energy"] = 0.0
                else:
                    initiator_client_energy_full_df[id]["energy"] = float(energy["watt"]*energy["runtime"])
            
        
            if id not in ids and temp["1"]["role"]== "responder" and id == energy['id']:
        
                responder_client_space_full_df[df["ID"][i]] = temp
                responder_client_energy_full_df[id] = {}
                #responder_client_energy_full_df[id]["powertop"] = df_energy["powertop"].iloc[i]
                responder_client_energy_full_df[id]["ram"] = energy["ram"]
                if math.isnan(float(energy["watt"]*energy["runtime"])):
                    responder_client_energy_full_df[id]["energy"] = 0
                else:
                    responder_client_energy_full_df[id]["energy"] = float(energy["watt"]*energy["runtime"])


    #iterate_nested_json_for_loop(temp)

        ls_in = []
        index=0
        for key, value in initiator_client_space_full_df.items():
            initiator ={}   
            counter = 0
            sum_time = 0
            sum_bandwidth = 0 
            initiator["ID"]=key
            for round, values in value.items():
        #print(round)
                sum_time += values["time"]
                sum_bandwidth += values["bandwidth_response"]        
                counter+=1
        
            initiator["time_space"] = sum_time 
            initiator["bandwidth_space"] = sum_bandwidth 
            initiator["round"] = counter+1
            initiator["domain"] = "space" 
            #initiator["powertop"] = initiator_client_energy_full_df[key]["powertop"]
            initiator["ram"] = initiator_client_energy_full_df[key]["ram"]
            initiator["energy"] = initiator_client_energy_full_df[key]["energy"]

            ls_in.append(initiator)
            index+=1

 
        ls_res = []
        index = 0
        for key, value in responder_client_space_full_df.items():
        #print(key,value)
            responder ={}  
            counter = 0
            sum_time = 0
            sum_bandwidth = 0 
            responder["ID"]=key
            for round, values in value.items():
        #print(round)
                sum_time += values["time"]
                sum_bandwidth += values["bandwidth"]        
                counter+=1
        
            responder["time_space"] = sum_time 
            responder["bandwidth_space"] = sum_bandwidth
            responder["round"] = counter 
            responder["domain"] = "space"
            #responder["powertop"] = responder_client_energy_full_df[key]["powertop"]
            responder["ram"] = responder_client_energy_full_df[key]["ram"]
            responder["energy"] = responder_client_energy_full_df[key]["energy"]
            ls_res.append(responder)
            index+=1

#print(initiator)


#iterate_nested_json_for_loop(json.loads(df['performance'][1]))
#print(json.loads(df['performance'][1]))
    #print(responder)

        df_initiator_client = pd.json_normalize(ls_in)
        df_responder_client = pd.json_normalize(ls_res)
        print(df_initiator_client)
        print(df_responder_client)
        j+=1
    return df_initiator_client, df_responder_client



def retrievedataenergynonco(df,df_energy):
    initiator_client_space_full_df = {}
    responder_client_space_full_df = {}
    initiator_client_energy_full_df = {}
    responder_client_energy_full_df = {}
    ids =[1273, 1939, 2400, 2674, 2752, 3692, 4450, 4733]
    if len(df) ==3229:
        length = len(df)-1
    else:
        length = len(df)
    j=0
    for index, energy in df_energy.iterrows():
        
        for i in range(0,length):
        
            temp = json.loads(df["performance"][i])
            id = df["ID"][i]
            if id not in ids and temp["1"]["role"]== "initiator" and id == energy['id']:
                initiator_client_space_full_df[df["ID"][i]] = temp
                initiator_client_energy_full_df[id] = {}
            #initiator_client_energy_full_df[id]["powertop"] = df_energy["powertop"].iloc[i]
                initiator_client_energy_full_df[id]["ram"] = energy["ram"]
                initiator_client_energy_full_df[id]["energy"] = energy["energy"]
            
        
            if id not in ids and temp["1"]["role"]== "responder" and id == energy['id']:
        
                responder_client_space_full_df[df["ID"][i]] = temp
                responder_client_energy_full_df[id] = {}
                #responder_client_energy_full_df[id]["powertop"] = df_energy["powertop"].iloc[i]
                responder_client_energy_full_df[id]["ram"] = energy["ram"]
                responder_client_energy_full_df[id]["energy"] = energy["energy"]


    #iterate_nested_json_for_loop(temp)

        ls_in = []
        index=0
        for key, value in initiator_client_space_full_df.items():
            initiator ={}   
            counter = 0
            sum_time = 0
            sum_bandwidth = 0 
            initiator["ID"]=key
            for round, values in value.items():
        #print(round)
                sum_time += values["time"]
                sum_bandwidth += values["bandwidth_response"]        
                counter+=1
        
            initiator["time_space"] = sum_time 
            initiator["bandwidth_space"] = sum_bandwidth 
            initiator["round"] = counter+1
            initiator["domain"] = "space" 
            #initiator["powertop"] = initiator_client_energy_full_df[key]["powertop"]
            initiator["ram"] = initiator_client_energy_full_df[key]["ram"]
            initiator["energy"] = initiator_client_energy_full_df[key]["energy"]

            ls_in.append(initiator)
            index+=1

 
        ls_res = []
        index = 0
        for key, value in responder_client_space_full_df.items():
        #print(key,value)
            responder ={}  
            counter = 0
            sum_time = 0
            sum_bandwidth = 0 
            responder["ID"]=key
            for round, values in value.items():
        #print(round)
                sum_time += values["time"]
                sum_bandwidth += values["bandwidth"]        
                counter+=1
        
            responder["time_space"] = sum_time 
            responder["bandwidth_space"] = sum_bandwidth
            responder["round"] = counter 
            responder["domain"] = "space"
            #responder["powertop"] = responder_client_energy_full_df[key]["powertop"]
            responder["ram"] = responder_client_energy_full_df[key]["ram"]
            responder["energy"] = responder_client_energy_full_df[key]["energy"]
            ls_res.append(responder)
            index+=1

#print(initiator)


#iterate_nested_json_for_loop(json.loads(df['performance'][1]))
#print(json.loads(df['performance'][1]))
    #print(responder)

        df_initiator_client = pd.json_normalize(ls_in)
        df_responder_client = pd.json_normalize(ls_res)
        print(df_initiator_client)
        print(df_responder_client)
        j+=1
    return df_initiator_client, df_responder_client


def extractram(directory_in_str,limit):
    # Initialize lists to hold data
    clients = []
    servers = []

# Regular expressions to match the lines
    server_pattern = re.compile(r'(\d+),server,\s*Parsed server ram usage:\s*(\d+)')
    client_pattern = re.compile(r'(\d+),client,\s*Parsed client ram usage:\s*(\d+)')
    directory = os.fsencode(directory_in_str)
    print(directory)

    #ids =[1273, 1939, 2400, 2674, 2752, 3692, 4450, 4733]
    counter = 0 
    alreadynot=False

    for file in os.listdir(directory):
        filename = os.fsdecode(file)
        print(filename)
        if filename.endswith(".log"): 
            counter += 1
            directory = os.fsdecode(directory)
            print(os.path.join(directory, filename))
            print(f"--- File: {directory+'/'+filename} ---")

            with open(directory+"/"+filename, 'r') as file:
                lines = file.readlines()
                total_lines = len(lines)
                print(f"Total number of lines: {total_lines}")
                
                for i, line in enumerate(lines):


                    server_match = server_pattern.search(line)
                    client_match = client_pattern.search(line)
    
                    if server_match:
                        id_number = server_match.group(1)
                        ram_usage = server_match.group(2)
                        servers.append({'id': id_number, 'role': 'server', 'ram': ram_usage})
    
                    if client_match:
                        id_number = client_match.group(1)
                        ram_usage = client_match.group(2)
                        clients.append({'id': id_number, 'role': 'client', 'ram': ram_usage})

# Create DataFrames
    clients_df = pd.DataFrame(clients)
    servers_df = pd.DataFrame(servers)

# Convert ram_usage to integer
    clients_df['ram'] = clients_df['ram'].astype(int)
    servers_df['ram'] = servers_df['ram'].astype(int)

    return clients_df,servers_df
