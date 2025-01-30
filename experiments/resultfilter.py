#!/usr/bin/env python3
import sys
import time


def filterresults(query_size, policy_size,share_distribution, result_path, filtered_file, memory_path, memory_filtered):
    #Setup phase

    filtered = open(filtered_file, "a")
    outcome = ""+str(query_size)+","+str(policy_size)+","
    setup_phase = share_distribution
    distribution = 0
    online_phase = 0
    bandwidth = 0
    ram = 0
    total = 0
    init = 0
    circuitgen = 0
    network = 0
    baseots = 0
    setup = 0
    otextension = 0
    garbling = 0
    online = 0
    total_sent = 0
    total_recv = 0
    baseot_sent = 0
    baseot_recv = 0
    setup_sent = 0
    setup_recv = 0
    otextension_sent = 0
    otextension_recv = 0
    garbling_sent = 0
    garbling_recv = 0
    online_sent = 0
    online_recv = 0

    #ram = ramusage(memory_path)
    with open(result_path, "r") as infile:
        for line in infile:
            
            
            
            if line[:7] == "Total =":
                words = line.split("\t")
                print(words)
                parts = words[2].split(" ")
                print(parts)
                total = float(parts[0])
                print(total)
            elif line[:6] == "Init =":
                words = line.split("\t")
                #print(words)
                parts = words[2].split(" ")
                print(parts)
                init = float(parts[0])
                setup_phase += float(parts[0])
                print(setup_phase)
            elif line[:12] == "CircuitGen =":
                 words = line.split("\t")
                 print(words)
                 parts = words[1].split(" ")
                 print(parts)
                 circuitgen = float(parts[0])
                 setup_phase += float(parts[0])
            elif line[:9] == "Network =":
                 words = line.split("\t")
                 print(words)
                 parts = words[1].split(" ")
                 print(parts)
                 network = float(parts[0])
            elif line[:9] == "BaseOTs =":
                 words = line.split("\t")
                 print(words)
                 parts = words[1].split(" ")
                 print(parts)
                 baseots = float(parts[0])
            elif line[:7] == "Setup =":
                 words = line.split("\t")
                 print(words)
                 parts = words[2].split(" ")
                 print(parts)
                 setup = float(parts[0])
            elif line[:10] == "Garbling =":
                 words = line.split("\t")
                 print(words)
                 parts = words[1].split(" ")
                 print(parts)
                 garbling = float(parts[0])
                 setup_phase += float(parts[0])
                 print(str(setup_phase))
                 #outcome = outcome+""+str(setup_phase)+", "
            elif line[:13] == "OTExtension =":
                 words = line.split("\t")
                 print(words)
                 parts = words[1].split(" ")
                 print(parts)
                 otextension = float(parts[0])
                 online_phase += float(parts[0])
            elif line[:8] == "Online =":
                 words = line.split("\t")
                 print(words)
                 parts = words[1].split(" ")
                 print(parts)
                 online = float(parts[0])
                 online_phase += float(parts[0])
                 #outcome = outcome+""+str(online_phase)+", "
                 print(str(online_phase))
            elif line[:10] == "Total Sent":
                words = line.split("\t")
                print(words)
                parts = words[1].split(" ")
                print(parts)
                bandwidth = int(parts[0])
                total_sent = int(parts[0])
                total_recv = int(parts[4])
            elif line[:12] == "BaseOTs Sent":
                words = line.split("\t")
                print(words)
                parts = words[1].split(" ")
                print(parts)
                baseot_sent = int(parts[0])
                baseot_recv = int(parts[4])
            elif line[:10] == "Setup Sent":
                words = line.split("\t")
                print(words)
                parts = words[1].split(" ")
                print(parts)
                setup_sent = int(parts[0])
                setup_recv = int(parts[4])
            elif line[:16] == "OTExtension Sent":
                words = line.split("\t")
                print(words)
                parts = words[1].split(" ")
                print(parts)
                otextension_sent = int(parts[0])
                otextension_recv = int(parts[4])
            elif line[:13] == "Garbling Sent":
                words = line.split("\t")
                print(words)
                parts = words[1].split(" ")
                print(parts)
                garbling_sent = int(parts[0])
                garbling_recv = int(parts[4])
            elif line[:11] == "Online Sent":
                words = line.split("\t")
                print(words)
                parts = words[1].split(" ")
                print(parts)
                online_sent = int(parts[0])
                online_recv = int(parts[4])
                #outcome = outcome+""+str(bandwidth)+", "

                
                #outcome = ""+str(query_size)+", "+str(policy_size)+", "
                #setup_phase = share_distribution
                #online_phase = 0
                #bandwidth = 0
                
            elif "setup: " in line:
                words = line.split(" ")
                print(float(words[1]))
                distribution = float(words[1])
                #outcome = outcome+""+str(setup_phase)+", "
                
                #ramfilter(memory_path,memory_filtered)
            elif "Maximum resident set size (kbytes):" in line:
                words = line.split(": ")
                print(words[1])
                ram = int(words[1])
                #outcome = outcome+""+str(words[1])

    outcome = outcome+""+str(total)+","+str(init)+","+str(circuitgen)+","+str(network)+","+str(baseots)+","+str(setup)+","+str(otextension)+","+str(garbling)+","+str(online)+","+str(total_sent)+","+str(total_recv)+","+str(baseot_sent)+","+str(baseot_recv)+","+str(setup_sent)+","+str(setup_recv)+","+str(otextension_sent)+","+str(otextension_recv)+","+str(garbling_sent)+","+str(garbling_recv)+","+str(online_sent)+","+str(online_recv)+","+str(distribution)+","+str(setup_phase)+","+str(round(online_phase,3))+","+str(bandwidth)+","+str(ram)
    f = open(filtered_file, "a")
    f.write(outcome+"\n")
    f.close()
    print(outcome+"\n")
                
                

    infile.close()


def ramavg(memory_path):
    count = 0
    ram = 0
    innercounter = 0
    with open(memory_path, "r") as infile:
        for line in infile:
            count+=1
            if count % 2 == 0: 
                parts = line.split(" ")
                print(parts)
                ram+=float(parts[1])
                innercounter +=1
    infile.close()
    return round(float(ram/innercounter),3)


def ramfilter(memory_path,memory_filtered):
    count = 0
    ram = 0
    with open(memory_path, "r") as infile:
        for line in infile:
            count+=1
            if count % 2 == 0: #this is the remainder operator
                print(line)
                parts = line.split(" ")
                print("PARTS: ")
                print(parts)
                f = open(memory_filtered,"a" )
                if len(parts) == 4 :
                    f.write(parts[1]+","+str(int(parts[2]))+","+str(int(parts[3]))+"\n")
                elif len(parts) == 5 :
                    f.write(parts[1]+","+str(int(parts[3]))+","+str(int(parts[4]))+"\n")
                
                elif len(parts) == 6 :
                    f.write(parts[1]+","+str(int(parts[4]))+","+str(int(parts[5]))+"\n")
                else:
                    print(parts[1]+","+str(int(parts[6]))+","+str(int(parts[7]))+"\n")
                f.close()
                
    infile.close()
    return round(float(ram/count),3)








