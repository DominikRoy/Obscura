import pandas as pd
import re
import numpy as np
import matplotlib.pyplot as plt
# Function to read and extract data from the file
def extract_data_from_file(file_path):
    # Initialize lists to hold the extracted values
    comp_time = []
    comm_time = []
    online_time = []
    communication_time = []

    # Variables for computation and communication time costs
    computation_time_cost = None
    communication_time_cost = None

    # Read the file
    with open(file_path, 'r') as file:
        content = file.readlines()

    # Iterate through each line and extract relevant information
    for line in content:
        # Extract Comp.Time, Comm.Time, Comp.Time
        comp_time_match = re.search(r'Comp.Time:\s*([+-]?\d+\.\d+([eE][+-]?\d+)?)', line)
        comm_time_match = re.search(r'Comm.Time:\s*(\d+\.\d+)', line)
        online_time_match = re.search(r'Online Time:\s*(\d+\.\d+)', line)
        online_time_match1 = re.search(r'OnlineTime:\s*(\d+\.\d+)', line)
        communication_time_match = re.search(r'Communication:\s*(\d+\.\d+)', line)
        communication_time_match1 = re.search(r'Communiction:\s*(\d+\.\d+)', line)
        communication_time_match2 = re.search(r'Firstround:\s*(\d+\.\d+)', line)
        comp_time_match_zero = re.search(r'Comp.Time:\s*(0)(?=\n)', line)



        if comp_time_match:
            print(comp_time_match)
            comp_time.append(float(comp_time_match.group(1))*1000)
        if comm_time_match:
            comm_time.append(float(comm_time_match.group(1))*1000)
        if online_time_match:
            online_time.append(float(online_time_match.group(1))*1000)
        if online_time_match1:
            online_time.append(float(online_time_match1.group(1))*1000)
        if communication_time_match:
            communication_time.append(float(communication_time_match.group(1))*1000)
        if communication_time_match1:
            communication_time.append(float(communication_time_match1.group(1))*1000)
        if communication_time_match2:
            communication_time.append(float(communication_time_match2.group(1))*1000)

        if comp_time_match_zero:
            print(comp_time_match_zero)
            comp_time.append(float(comp_time_match_zero.group(1))*1000)


        # Extract computation and communication time costs
        if 'Compuation time cost is:' in line:
            computation_time_cost = float(line.split(':')[-1].strip())
        if 'Commu. time cost is:' in line:
            communication_time_cost = float(line.split(':')[-1].strip())

    # Create a DataFrame from the lists
    print(len(comp_time))
    print(len(comm_time))
    print(len(online_time))
    print(len(communication_time))
    df = pd.DataFrame({
        'Comp.Time': comp_time,
        'Comm.Time': comm_time,
        'Online Time': online_time,
        'Communication Time': communication_time
    })

    return df, computation_time_cost, communication_time_cost

# Specify the path to your text file
data_10_0_leak = 'executiontime/server_leak_10mbits_server0_32_input_2.txt'  # Change this to your actual file path
data_10_1_leak = 'executiontime/server_leak_10mbits_server1_32_input_2.txt'  # Change this to your actual file path
data_100_0_leak = 'executiontime/server_leak_10mbits_server0_64_input_2.txt'  # Change this to your actual file path
data_100_1_leak = 'executiontime/server_leak_10mbits_server1_64_input_2.txt'  # Change this to your actual file path
data_1_0_leak = 'executiontime/server_leak_10mbits_server0_128_input_2.txt'  # Change this to your actual file path
data_1_1_leak = 'executiontime/server_leak_10mbits_server1_128_input_2.txt'  # Change this to your actual file path
data_10_0 = 'executiontime/server_10mbits_server0_32_input_2.txt'  # Change this to your actual file path
data_10_1 = 'executiontime/server_10mbits_server1_32_input_2.txt'  # Change this to your actual file path
data_100_0 = 'executiontime/server_10mbits_server0_64_input_2.txt'  # Change this to your actual file path
data_100_1 = 'executiontime/server_10mbits_server1_64_input_2.txt'  # Change this to your actual file path
data_1_0 = 'executiontime/server_10mbits_server0_128_input_2.txt'  # Change this to your actual file path
data_1_1 = 'executiontime/server_10mbits_server1_128_input_2.txt'  # Change this to your actual file path
data_rpi_server_drone_ours = 'executiontime_new/RPI/server_leak_64bits_bytes.txt'
data_rpi_client_md_ours = 'executiontime_new/RPI/client_leak_64bits_bytes.txt'
data_rpi_server_drone_asiaccs = 'executiontime_new/RPI/server_64bits_bytes.txt'
data_rpi_client_md_asiaccs = 'executiontime_new/RPI/client_64bits_bytes.txt'


new_drone_leak = 'executiontime/server_leak_64bits_exec_Jan15_1.txt'
new_drone = 'executiontime/server_64bits_exec_Jan14.txt'
new_md_leak = 'executiontime/client_leak_64bits_exec_Jan15_1.txt'
new_md = 'executiontime/client_64bits_exec_Jan14.txt'

new_drone_leak_intel = 'executiontime/server_intel_leak_newv1.txt'
new_drone_intel = 'executiontime/server_intel.txt'
new_md_leak_intel = 'executiontime/client_intel_leak_newv1.txt'
new_md_intel = 'executiontime/client_intel.txt'




# Extract the data
data_df_10_0_leak, computation_cost_10_0_leak, communication_cost_10_0_leak = extract_data_from_file(data_10_0_leak)
data_df_10_1_leak, computation_cost_10_1_leak, communication_cost_10_1_leak = extract_data_from_file(data_10_1_leak)
data_df_100_0_leak, computation_cost_100_0_leak, communication_cost_100_0_leak = extract_data_from_file(data_100_0_leak)
data_df_100_1_leak, computation_cost_10_0_leak, communication_cost_10_0_leak = extract_data_from_file(data_100_1_leak)
data_df_1_0_leak, computation_cost_1_0_leak, communication_cost_1_0_leak = extract_data_from_file(data_1_0_leak)
data_df_1_1_leak, computation_cost_1_1_leak, communication_cost_1_1_leak = extract_data_from_file(data_1_1_leak)
data_df_10_0, computation_cost_10_0, communication_cost_10_0 = extract_data_from_file(data_10_0)
data_df_10_1, computation_cost_10_1, communication_cost_10_1 = extract_data_from_file(data_10_1)
data_df_100_0, computation_cost_100_0, communication_cost_100_0 = extract_data_from_file(data_100_0)
data_df_100_1, computation_cost_10_0, communication_cost_10_0 = extract_data_from_file(data_100_1)
data_df_1_0, computation_cost_1_0, communication_cost_1_0 = extract_data_from_file(data_1_0)
data_df_1_1, computation_cost_1_1, communication_cost_1_1 = extract_data_from_file(data_1_1)


data_ours_0, computation_cost_ours, communication_cost_ours = extract_data_from_file(data_rpi_server_drone_ours)
data_ours_1, computation_cost_ours, communication_cost_ours = extract_data_from_file(data_rpi_client_md_ours)
data_asia_0, computation_cost_asia, communication_cost_asia = extract_data_from_file(data_rpi_server_drone_asiaccs)
data_asia_1, computation_cost_asia, communication_cost_asia = extract_data_from_file(data_rpi_client_md_asiaccs)



new_drone_leak_df, comp_leak_drone, comm_leak_drone = extract_data_from_file(new_drone_leak) 
new_md_leak_df, comp_leak_md, comm_leak_md = extract_data_from_file(new_md_leak)
new_drone_df, comp_drone, comm_drone = extract_data_from_file(new_drone)
new_md_df, comp_md, comm_md = extract_data_from_file(new_md)

new_drone_leak_df_intel, comp_leak_drone_intel, comm_leak_drone_intel = extract_data_from_file(new_drone_leak_intel) 
new_md_leak_df_intel, comp_leak_md_intel, comm_leak_md_intel= extract_data_from_file(new_md_leak_intel)
new_drone_df_intel, comp_drone_intel, comm_drone_intel = extract_data_from_file(new_drone_intel)
new_md_df_intel, comp_md_intel, comm_md_intel = extract_data_from_file(new_md_intel)







# Calculate the mean and the 95% confidence interval
mean = data_df_10_0_leak['Online Time'].mean()
std = data_df_10_0_leak['Online Time'].std()
n = len(data_df_10_0_leak['Online Time'])
ci = 1.96 * (std / np.sqrt(n))  # 95% CI is approximately 1.96 * SE

# Create a new DataFrame for mean and CI
data_df_10_0_leakmean = mean
data_df_10_0_leaklci = mean - ci
data_df_10_0_leakuci = mean + ci


# Calculate the mean and the 95% confidence interval
mean = data_df_10_1_leak['Online Time'].mean()
std = data_df_10_1_leak['Online Time'].std()
n = len(data_df_10_1_leak['Online Time'])
ci = 1.96 * (std / np.sqrt(n))  # 95% CI is approximately 1.96 * SE

# Create a new DataFrame for mean and CI
data_df_10_1_leakmean = mean
data_df_10_1_leaklci = mean - ci
data_df_10_1_leakuci = mean + ci

# Calculate the mean and the 95% confidence interval
mean = data_df_100_0_leak['Online Time'].mean()
std = data_df_100_0_leak['Online Time'].std()
n = len(data_df_100_0_leak['Online Time'])
ci = 1.96 * (std / np.sqrt(n))  # 95% CI is approximately 1.96 * SE

# Create a new DataFrame for mean and CI
data_df_100_0_leakmean = mean
data_df_100_0_leaklci = mean - ci
data_df_100_0_leakuci = mean + ci


# Calculate the mean and the 95% confidence interval
mean = data_df_100_1_leak['Online Time'].mean()
std = data_df_100_1_leak['Online Time'].std()
n = len(data_df_100_1_leak['Online Time'])
ci = 1.96 * (std / np.sqrt(n))  # 95% CI is approximately 1.96 * SE

# Create a new DataFrame for mean and CI
data_df_100_1_leakmean = mean
data_df_100_1_leaklci = mean - ci
data_df_100_1_leakuci = mean + ci

# Calculate the mean and the 95% confidence interval
mean = data_df_1_0_leak['Online Time'].mean()
std = data_df_1_0_leak['Online Time'].std()
n = len(data_df_1_0_leak['Online Time'])
ci = 1.96 * (std / np.sqrt(n))  # 95% CI is approximately 1.96 * SE

# Create a new DataFrame for mean and CI
data_df_1_0_leakmean = mean
data_df_1_0_leaklci = mean - ci
data_df_1_0_leakuci = mean + ci


# Calculate the mean and the 95% confidence interval
mean = data_df_1_1_leak['Online Time'].mean()
std = data_df_1_1_leak['Online Time'].std()
n = len(data_df_1_1_leak['Online Time'])
ci = 1.96 * (std / np.sqrt(n))  # 95% CI is approximately 1.96 * SE

# Create a new DataFrame for mean and CI
data_df_1_1_leakmean = mean
data_df_1_1_leaklci = mean - ci
data_df_1_1_leakuci = mean + ci


# Calculate the mean and the 95% confidence interval
mean = data_df_10_0['Online Time'].mean()
std = data_df_10_0['Online Time'].std()
n = len(data_df_10_0['Online Time'])
ci = 1.96 * (std / np.sqrt(n))  # 95% CI is approximately 1.96 * SE

# Create a new DataFrame for mean and CI
data_df_10_0mean = mean
data_df_10_0lci = mean - ci
data_df_10_0uci = mean + ci


# Calculate the mean and the 95% confidence interval
mean = data_df_10_1['Online Time'].mean()
std = data_df_10_1['Online Time'].std()
n = len(data_df_10_1['Online Time'])
ci = 1.96 * (std / np.sqrt(n))  # 95% CI is approximately 1.96 * SE

# Create a new DataFrame for mean and CI
data_df_10_1mean = mean
data_df_10_1lci = mean - ci
data_df_10_1uci = mean + ci

# Calculate the mean and the 95% confidence interval
mean = data_df_100_0['Online Time'].mean()
std = data_df_100_0['Online Time'].std()
n = len(data_df_100_0['Online Time'])
ci = 1.96 * (std / np.sqrt(n))  # 95% CI is approximately 1.96 * SE

# Create a new DataFrame for mean and CI
data_df_100_0mean = mean
data_df_100_0lci = mean - ci
data_df_100_0uci = mean + ci


# Calculate the mean and the 95% confidence interval
mean = data_df_100_1['Online Time'].mean()
std = data_df_100_1['Online Time'].std()
n = len(data_df_100_1['Online Time'])
ci = 1.96 * (std / np.sqrt(n))  # 95% CI is approximately 1.96 * SE

# Create a new DataFrame for mean and CI
data_df_100_1mean = mean
data_df_100_1lci = mean - ci
data_df_100_1uci = mean + ci

# Calculate the mean and the 95% confidence interval
mean = data_df_1_0['Online Time'].mean()
std = data_df_1_0['Online Time'].std()
n = len(data_df_1_0['Online Time'])
ci = 1.96 * (std / np.sqrt(n))  # 95% CI is approximately 1.96 * SE

# Create a new DataFrame for mean and CI
data_df_1_0mean = mean
data_df_1_0lci = mean - ci
data_df_1_0uci = mean + ci


# Calculate the mean and the 95% confidence interval
mean = data_df_1_1['Online Time'].mean()
std = data_df_1_1['Online Time'].std()
n = len(data_df_1_1['Online Time'])
ci = 1.96 * (std / np.sqrt(n))  # 95% CI is approximately 1.96 * SE

# Create a new DataFrame for mean and CI
data_df_1_1mean = mean
data_df_1_1lci = mean - ci
data_df_1_1uci = mean + ci



# Calculate the mean and the 95% confidence interval
mean = data_ours_0['Online Time'].mean()
std = data_ours_0['Online Time'].std()
n = len(data_ours_0['Online Time'])
ci = 1.96 * (std / np.sqrt(n))  # 95% CI is approximately 1.96 * SE

# Create a new DataFrame for mean and CI
data_ours_0mean = mean
data_ours_0lci = mean - ci
data_ours_0uci = mean + ci


# Calculate the mean and the 95% confidence interval
mean = data_ours_1['Online Time'].mean()
std = data_ours_1['Online Time'].std()
n = len(data_ours_1['Online Time'])
ci = 1.96 * (std / np.sqrt(n))  # 95% CI is approximately 1.96 * SE

# Create a new DataFrame for mean and CI
data_ours_1mean = mean
data_ours_1lci = mean - ci
data_ours_1uci = mean + ci


# Calculate the mean and the 95% confidence interval
mean = data_asia_0['Online Time'].mean()
std = data_asia_0['Online Time'].std()
n = len(data_asia_0['Online Time'])
ci = 1.96 * (std / np.sqrt(n))  # 95% CI is approximately 1.96 * SE

# Create a new DataFrame for mean and CI
data_asia_0mean = mean
data_asia_0lci = mean - ci
data_asia_0uci = mean + ci


# Calculate the mean and the 95% confidence interval
mean = data_asia_1['Online Time'].mean()
std = data_asia_1['Online Time'].std()
n = len(data_asia_1['Online Time'])
ci = 1.96 * (std / np.sqrt(n))  # 95% CI is approximately 1.96 * SE

# Create a new DataFrame for mean and CI
data_asia_1mean = mean
data_asia_1lci = mean - ci
data_asia_1uci = mean + ci











print([data_df_10_1lci,data_df_100_1lci,data_df_1_1lci],[data_df_10_1uci,data_df_100_1uci,data_df_1_1uci])
print([data_df_10_0lci,data_df_100_0lci,data_df_1_0lci],[data_df_10_0uci,data_df_100_0uci,data_df_1_0uci])
print([data_df_10_1_leaklci,data_df_100_1_leaklci,data_df_1_1_leaklci],[data_df_10_1_leakuci,data_df_100_1_leakuci,data_df_1_1_leakuci])
print([data_df_10_0_leaklci,data_df_100_0_leaklci,data_df_1_0_leaklci],[data_df_10_0_leakuci,data_df_100_0_leakuci,data_df_1_0_leakuci])
print([data_df_10_1mean,data_df_100_1mean,data_df_1_1mean])
print([data_df_10_0mean,data_df_100_0mean,data_df_1_0mean])
print([data_df_10_1_leakmean,data_df_100_1_leakmean,data_df_1_1_leakmean])
print( [data_df_10_0_leakmean,data_df_100_0_leakmean,data_df_1_0_leakmean])


fig, ax  = plt.subplots(figsize=(14, 7))
# Plotting


ax.fill_between(["32 Bits", "64 Bits", "128 Bits"], [data_df_10_1lci,data_df_100_1lci,data_df_1_1lci],[data_df_10_1uci,data_df_100_1uci,data_df_1_1uci] , color='#98df8a', alpha=0.5, label='95% Confidence Interval AsiaCSS Client')
ax.fill_between(["32 Bits", "64 Bits", "128 Bits"], [data_df_10_0lci,data_df_100_0lci,data_df_1_0lci],[data_df_10_0uci,data_df_100_0uci,data_df_1_0uci], color='#c5b0d5', alpha=0.5, label='95% Confidence Interval AsiaCSS Server')
ax.fill_between(["32 Bits", "64 Bits", "128 Bits"], [data_df_10_1_leaklci,data_df_100_1_leaklci,data_df_1_1_leaklci],[data_df_10_1_leakuci,data_df_100_1_leakuci,data_df_1_1_leakuci] , color='#aec7e8', alpha=0.5, label='95% Confidence Interval ours Client')
ax.fill_between(["32 Bits", "64 Bits", "128 Bits"], [data_df_10_0_leaklci,data_df_100_0_leaklci,data_df_1_0_leaklci],[data_df_10_0_leakuci,data_df_100_0_leakuci,data_df_1_0_leakuci] , color='#ff9896', alpha=0.5, label='95% Confidence Interval ours Server')

ax.plot(["32 Bits", "64 Bits", "128 Bits"], [data_df_10_1mean,data_df_100_1mean,data_df_1_1mean], label='AsiaCCS Client',color='#2ca02c')
ax.plot(["32 Bits", "64 Bits", "128 Bits"], [data_df_10_0mean,data_df_100_0mean,data_df_1_0mean], label='AsiaCCS Server',color='#9467bd')
ax.plot(["32 Bits", "64 Bits", "128 Bits"], [data_df_10_1_leakmean,data_df_100_1_leakmean,data_df_1_1_leakmean], label='Ours Client', color='#1f77b4')
ax.plot(["32 Bits", "64 Bits", "128 Bits"], [data_df_10_0_leakmean,data_df_100_0_leakmean,data_df_1_0_leakmean], label='Ours Server', color='#d62728')
ax.set_title('Mean and 95% Confidence Interval')
ax.set_xlabel('Input Length')
ax.set_ylabel('Executiontime [ms]')
#ax.set_yscale('log')
ax.grid(True)
ax.legend()
plt.show()

testbeds = ("T1", "T2")
entities_means = {
    'MD - LIPPBV': (data_ours_1mean, data_ours_1mean),
    'Drone - LIPPBV': (data_ours_0mean, data_ours_0mean),
    'MD - [2]': (data_asia_1mean, data_asia_1mean),
    'Drone - [2]': (data_asia_0mean, data_asia_0mean),

}
print(entities_means)
x = np.arange(len(testbeds))  # the label locations
width = 0.25  # the width of the bars
multiplier = 0

fig, ax = plt.subplots(layout='constrained')

for attribute, measurement in entities_means.items():
    offset = width * multiplier
    rects = ax.bar(x + offset, measurement, width, label=attribute)
    ax.bar_label(rects, padding=3)
    multiplier += 1

# Add some text for labels, title and custom x-axis tick labels, etc.
ax.set_ylabel('Executiontime [ms]')
ax.set_title('Execution time  by Testbeds')
ax.set_xticks(x + width, testbeds)
ax.legend(loc='upper left', bbox_to_anchor=(1, 1))
ax.set_ylim(0, 250)
plt.show()
fig, ax  = plt.subplots(figsize=(14, 7))
# Plotting


#ax.fill_between(["32 Bits", "64 Bits", "128 Bits"], [data_df_10_1lci,data_df_100_1lci,data_df_1_1lci],[data_df_10_1uci,data_df_100_1uci,data_df_1_1uci] , color='#98df8a', alpha=0.5, label='95% Confidence Interval AsiaCSS Client')
#ax.fill_between(["32 Bits", "64 Bits", "128 Bits"], [data_df_10_0lci,data_df_100_0lci,data_df_1_0lci],[data_df_10_0uci,data_df_100_0uci,data_df_1_0uci], color='#c5b0d5', alpha=0.5, label='95% Confidence Interval AsiaCSS Server')
#ax.fill_between(["32 Bits", "64 Bits", "128 Bits"], [data_df_10_1_leaklci,data_df_100_1_leaklci,data_df_1_1_leaklci],[data_df_10_1_leakuci,data_df_100_1_leakuci,data_df_1_1_leakuci] , color='#aec7e8', alpha=0.5, label='95% Confidence Interval ours Client')
#ax.fill_between(["32 Bits", "64 Bits", "128 Bits"], [data_df_10_0_leaklci,data_df_100_0_leaklci,data_df_1_0_leaklci],[data_df_10_0_leakuci,data_df_100_0_leakuci,data_df_1_0_leakuci] , color='#ff9896', alpha=0.5, label='95% Confidence Interval ours Server')

ax.plot(data_asia_1['Communication Time'], label='AsiaCCS Client',color='#2ca02c')
ax.plot(data_asia_0['Communication Time'], label='AsiaCCS Server',color='#9467bd')
ax.plot(data_ours_1['Communication Time'], label='Ours Client', color='#1f77b4')
ax.plot(  data_ours_0['Communication Time'], label='Ours Server', color='#d62728')
ax.set_title('Mean and 95% Confidence Interval')
ax.set_xlabel('Input Length')
ax.set_ylabel('Executiontime [ms]')
#ax.set_yscale('log')
ax.grid(True)
ax.legend()
plt.show()


# Print the DataFrame and the costs
#print(data_df_10_0)
#print(f'Computation Time Cost: {computation_cost}')
#print(f'Communication Time Cost: {communication_cost}')





labels = ['Obscura', 'Cheng et al.']
group1 = [3, 5]
group2 = [3, 3]
group1_sub1 = [new_drone_leak_df['Comm.Time'].mean(), new_drone_df['Comm.Time'].mean()]  # Sub-category for group 1
group1_sub2 = [new_drone_leak_df['Comp.Time'].mean(), new_drone_df['Comp.Time'].mean()]  # Sub-category for group 1
group2_sub1 = [new_md_leak_df['Comm.Time'].mean(), new_md_df['Comm.Time'].mean()]  # Sub-category for group 2
group2_sub2 = [new_md_leak_df['Comp.Time'].mean(), new_md_df['Comp.Time'].mean()]  # Sub-category for group 2



new_drone_leak_df['Total'] = new_drone_leak_df['Comm.Time'] + new_drone_leak_df['Comp.Time']
new_drone_df['Total'] = new_drone_df['Comm.Time'] + new_drone_df['Comp.Time']
new_md_leak_df['Total'] = new_md_leak_df['Comm.Time'] + new_md_leak_df['Comp.Time']
new_md_df['Total'] = new_md_df['Comm.Time'] + new_md_df['Comp.Time']
# Calculate the mean and the 95% confidence interval
mean = new_drone_leak_df['Total'].mean()
std = new_drone_leak_df['Total'].std()
n = len(new_drone_leak_df['Total'])
ci = 1.96 * (std / np.sqrt(n))  # 95% CI is approximately 1.96 * SE

# Create a new DataFrame for mean and CI
df_drone_exec_leakmean = mean
df_drone_exec_leaklci = mean - ci
df_drone_exec_leakuci = mean + ci


# Calculate the mean and the 95% confidence interval
mean = new_drone_df['Total'].mean()
std = new_drone_df['Total'].std()
n = len(new_drone_df['Total'])
ci = 1.96 * (std / np.sqrt(n))  # 95% CI is approximately 1.96 * SE

# Create a new DataFrame for mean and CI
df_drone_exec_mean = mean
df_drone_exec_lci = mean - ci
df_drone_exec_uci = mean + ci


mean = new_md_leak_df['Total'].mean()
std = new_md_leak_df['Total'].std()
n = len(new_md_leak_df['Total'])
ci = 1.96 * (std / np.sqrt(n))  # 95% CI is approximately 1.96 * SE

# Create a new DataFrame for mean and CI
df_md_exec_leakmean = mean
df_md_exec_leaklci = mean - ci
df_md_exec_leakuci = mean + ci


# Calculate the mean and the 95% confidence interval
mean = new_md_df['Total'].mean()
std = new_md_df['Total'].std()
n = len(new_md_df['Total'])
ci = 1.96 * (std / np.sqrt(n))  # 95% CI is approximately 1.96 * SE

# Create a new DataFrame for mean and CI
df_md_exec_mean = mean
df_md_exec_lci = mean - ci
df_md_exec_uci = mean + ci





conf_int1 = [df_drone_exec_leakuci-df_drone_exec_leaklci, df_drone_exec_uci-df_drone_exec_lci]
conf_int2 = [df_md_exec_leakuci-df_md_exec_leaklci, df_md_exec_uci-df_md_exec_lci]
















# Set the number of groups and bar width
n_groups = len(labels)
bar_width = 0.2  # width of a single group

# Create the figure and axis
fig, ax = plt.subplots()

# Create the positions for each group
indices = np.arange(n_groups)
# Define colors for each bar
colors_group1_sub1 = 'darkgray'
colors_group1_sub2 = 'gray'
colors_group2_sub1 = 'darkgray'
colors_group2_sub2 = 'gray'
# Create first stacked bar for group 1
print(group1_sub1)
print(group1_sub2)
print(group2_sub1)
print(group2_sub2)
p1 = ax.bar(indices, group1_sub1, bar_width, label='Drone - Comm.Time', color=colors_group1_sub1)
p2 = ax.bar(indices, group1_sub2, bar_width, bottom=group1_sub1, label='Drone - Comp.Time',color=colors_group1_sub2,yerr=conf_int1,capsize=5)

# Create second stacked bar for group 2, offset by bar_width
p3 = ax.bar(indices + bar_width, group2_sub1, bar_width, label='WD - Comm.Time',color=colors_group2_sub1, hatch='\\')
p4 = ax.bar(indices + bar_width, group2_sub2, bar_width, bottom=group2_sub1, label='WD - Comp.Time', color=colors_group2_sub2, hatch='\\',yerr=conf_int2,capsize=5)

# Add labels, title, and custom x-axis tick labels
ax.set_xlabel('Schemes', fontsize = 14)
ax.set_ylabel('Execution Time [ms]', fontsize = 14)
#ax.set_title('Grouped Stacked Bar Plot Example')
ax.set_xticks(indices + bar_width/ 2)
ax.set_xticklabels(labels, fontsize = 14)
ax.tick_params(axis='y', labelsize=14)
ax.legend(fontsize = 14)
ax.grid('on')
# Display the plot
plt.tight_layout()
plt.show()

import os
import filterenergyram as fram


#N = 30  # Number of lines to print from each file
#for filename in filenames:
#    print_file_info(filename)
df_client_energy_cheng,df_server_energy_cheng = fram.extract_ram_energy_without_watt('newenergy',1000,True)
df_client_energy_leak,df_server_energy_leak = fram.extract_ram_energy_without_watt('newenergyleak',1000,True)
print(df_client_energy_cheng,df_server_energy_cheng)
print(df_client_energy_leak,df_server_energy_leak)
value_column1 = df_server_energy_leak.loc[498, 'ram']
print(value_column1)
print(new_drone_df,new_md_df)
print(new_drone_leak_df,new_md_leak_df)
new_md_df['Total']= new_md_df['Total']/1000
df_client_energy_cheng['energyv2'] = df_client_energy_cheng['watt']*new_md_df['Total']

new_drone_df['Total']= new_drone_df['Total']/1000
df_server_energy_cheng['energyv2'] = df_server_energy_cheng['watt']*new_drone_df['Total']

new_md_leak_df['Total']= new_md_leak_df['Total']/1000
df_client_energy_leak['energyv2'] = df_client_energy_leak['watt']*new_md_leak_df['Total']

new_drone_leak_df['Total']= new_drone_leak_df['Total']/1000
df_server_energy_leak['energyv2'] = df_server_energy_leak['watt']*new_drone_leak_df['Total']
print(df_client_energy_cheng,df_server_energy_cheng)
print(df_client_energy_leak,df_server_energy_leak)

print(new_drone_df,new_md_df)
print(new_drone_leak_df,new_md_leak_df)

df_client_energy_cheng['ram']= df_client_energy_cheng['ram']/1000
df_server_energy_cheng['ram']= df_server_energy_cheng['ram']/1000
df_client_energy_leak['ram']= df_client_energy_leak['ram']/1000
df_server_energy_leak['ram']= df_server_energy_leak['ram']/1000




# Calculate the mean and the 95% confidence interval
mean = df_client_energy_cheng['energyv2'].mean()
std = df_client_energy_cheng['energyv2'].std()
n = len(df_client_energy_cheng['energyv2'])
ci = 1.96 * (std / np.sqrt(n))  # 95% CI is approximately 1.96 * SE

# Create a new DataFrame for mean and CI
df_client_energy_chengmean = mean
df_client_energy_chenglci = mean - ci
df_client_energy_chenguci = mean + ci


# Calculate the mean and the 95% confidence interval
mean = df_client_energy_cheng['ram'].mean()
std = df_client_energy_cheng['ram'].std()
n = len(df_client_energy_cheng['ram'])
ci = 1.96 * (std / np.sqrt(n))  # 95% CI is approximately 1.96 * SE

# Create a new DataFrame for mean and CI
df_client_ram_chengmean = mean
df_client_ram_chenglci = mean - ci
df_client_ram_chenguci = mean + ci


# Calculate the mean and the 95% confidence interval
mean = df_server_energy_cheng['energyv2'].mean()
std = df_server_energy_cheng['energyv2'].std()
n = len(df_server_energy_cheng['energyv2'])
ci = 1.96 * (std / np.sqrt(n))  # 95% CI is approximately 1.96 * SE

# Create a new DataFrame for mean and CI
df_server_energy_chengmean = mean
df_server_energy_chenglci = mean - ci
df_server_energy_chenguci = mean + ci


# Calculate the mean and the 95% confidence interval
mean = df_server_energy_cheng['ram'].mean()
std = df_server_energy_cheng['ram'].std()
n = len(df_server_energy_cheng['ram'])
ci = 1.96 * (std / np.sqrt(n))  # 95% CI is approximately 1.96 * SE

# Create a new DataFrame for mean and CI
df_server_ram_chengmean = mean
df_server_ram_chenglci = mean - ci
df_server_ram_chenguci = mean + ci


# Calculate the mean and the 95% confidence interval
mean = df_client_energy_leak['energyv2'].mean()
std = df_client_energy_leak['energyv2'].std()
n = len(df_client_energy_leak['energyv2'])
ci = 1.96 * (std / np.sqrt(n))  # 95% CI is approximately 1.96 * SE

# Create a new DataFrame for mean and CI
df_client_energy_leakmean = mean
df_client_energy_leaklci = mean - ci
df_client_energy_leakuci = mean + ci


# Calculate the mean and the 95% confidence interval
mean = df_client_energy_leak['ram'].mean()
std = df_client_energy_leak['ram'].std()
n = len(df_client_energy_leak['ram'])
ci = 1.96 * (std / np.sqrt(n))  # 95% CI is approximately 1.96 * SE

# Create a new DataFrame for mean and CI
df_client_ram_leakmean = mean
df_client_ram_leaklci = mean - ci
df_client_ram_leakuci = mean + ci


# Calculate the mean and the 95% confidence interval
mean = df_server_energy_leak['energyv2'].mean()
std = df_server_energy_leak['energyv2'].std()
n = len(df_server_energy_leak['energyv2'])
ci = 1.96 * (std / np.sqrt(n))  # 95% CI is approximately 1.96 * SE

# Create a new DataFrame for mean and CI
df_server_energy_leakmean = mean
df_server_energy_leaklci = mean - ci
df_server_energy_leakuci = mean + ci


# Calculate the mean and the 95% confidence interval
mean = df_server_energy_leak['ram'].mean()
std = df_server_energy_leak['ram'].std()
n = len(df_server_energy_leak['ram'])
ci = 1.96 * (std / np.sqrt(n))  # 95% CI is approximately 1.96 * SE

# Create a new DataFrame for mean and CI
df_server_ram_leakmean = mean
df_server_ram_leaklci = mean - ci
df_server_ram_leakuci = mean + ci


labels = ['Obscura', 'Cheng et al.']

data1 = [df_server_energy_leakmean, df_server_energy_chengmean]
data2 = [df_client_energy_leakmean, df_client_energy_chengmean]
# Sample confidence intervals
conf_int1 = [df_server_energy_leakuci-df_server_energy_leaklci, df_server_energy_chenguci-df_server_energy_chenglci]
conf_int2 = [df_client_energy_leakuci-df_client_energy_leaklci, df_client_energy_chenguci-df_client_energy_chenglci]
# Set the number of groups and bar width
n_groups = len(labels)
bar_width = 0.2  # width of a single group

print(data1)
print(data2)

print(conf_int1)
print(conf_int2)

# Create the figure and axis
fig, ax = plt.subplots()

# Create the positions for each group
indices = np.arange(n_groups)
# Define colors for each bar
colors_group1_sub1 = 'gray'
#colors_group1_sub2 = 'lightgreen'
colors_group2_sub1 = 'darkgray'
#colors_group2_sub2 = 'orange'
# Create first stacked bar for group 1

p1 = ax.bar(indices, data1, bar_width, label='Drone', yerr=conf_int1,capsize=5, color=colors_group1_sub1 , alpha=0.7)
#p2 = ax.bar(indices, group1_sub2, bar_width, bottom=group1_sub1, label='Drone - Comp.Time',color=colors_group1_sub2)

# Create second stacked bar for group 2, offset by bar_width
p3 = ax.bar(indices + bar_width, data2, bar_width,  label='WD', yerr=conf_int2, capsize=5, color=colors_group2_sub1, alpha=0.7, hatch='\\')
#p4 = ax.bar(indices + bar_width, group2_sub2, bar_width, bottom=group2_sub1, label='MD - Comp.Time', color=colors_group2_sub2)

# Add labels, title, and custom x-axis tick labels
ax.set_xlabel('Schemes',fontsize = 14)
ax.set_ylabel('Energy Consumption [J]',fontsize = 14)
#ax.set_title('Grouped Stacked Bar Plot Example')
ax.set_xticks(indices + bar_width/ 2)
ax.set_xticklabels(labels,fontsize = 14)
ax.tick_params(axis='y', labelsize=14)
ax.legend(fontsize = 14)
ax.grid('on')
# Display the plot
plt.tight_layout()
plt.show()





labels = ['Obscura', 'Cheng et al.']

data1 = [df_server_ram_leakmean, df_server_ram_chengmean]
data2 = [df_client_ram_leakmean, df_client_ram_chengmean]
# Sample confidence intervals
conf_int1 = [df_server_ram_leakuci-df_server_ram_leaklci, df_server_ram_chenguci-df_server_ram_chenglci]
conf_int2 = [df_client_ram_leakuci-df_client_ram_leaklci, df_client_ram_chenguci-df_client_ram_chenglci]
# Set the number of groups and bar width
n_groups = len(labels)
bar_width = 0.2  # width of a single group

print(data1)
print(data2)

print(conf_int1)
print(conf_int2)

# Create the figure and axis
fig, ax = plt.subplots()

# Create the positions for each group
indices = np.arange(n_groups)
# Define colors for each bar
colors_group1_sub1 = 'gray'
#colors_group1_sub2 = 'lightgreen'
colors_group2_sub1 = 'darkgray'
#colors_group2_sub2 = 'orange'
# Create first stacked bar for group 1

p1 = ax.bar(indices, data1, bar_width, label='Drone', yerr=conf_int1,capsize=5, color=colors_group1_sub1 , alpha=0.7)
#p2 = ax.bar(indices, group1_sub2, bar_width, bottom=group1_sub1, label='Drone - Comp.Time',color=colors_group1_sub2)

# Create second stacked bar for group 2, offset by bar_width
p3 = ax.bar(indices + bar_width, data2, bar_width,  label='WD', yerr=conf_int2, capsize=5, color=colors_group2_sub1, alpha=0.7, hatch='\\')
#p4 = ax.bar(indices + bar_width, group2_sub2, bar_width, bottom=group2_sub1, label='MD - Comp.Time', color=colors_group2_sub2)

# Add labels, title, and custom x-axis tick labels
ax.set_xlabel('Schemes',fontsize = 14)
ax.set_ylabel('RAM Consumption [Mbytes]',fontsize = 14)
#ax.set_title('Grouped Stacked Bar Plot Example')
ax.set_xticks(indices + bar_width/ 2)
ax.set_xticklabels(labels,fontsize = 14)
ax.tick_params(axis='y', labelsize=14)
ax.legend(loc=9,fontsize = 14)
ax.grid('on')
# Display the plot
plt.tight_layout()
plt.show()



###INTEL

labels = ['Obscura', 'Cheng et al.']
group1 = [3, 5]
group2 = [3, 3]
group1_sub1 = [new_drone_leak_df_intel['Comm.Time'].mean(), new_drone_df_intel['Comm.Time'].mean()]  # Sub-category for group 1
group1_sub2 = [new_drone_leak_df_intel['Comp.Time'].mean(), new_drone_df_intel['Comp.Time'].mean()]  # Sub-category for group 1
group2_sub1 = [new_md_leak_df_intel['Comm.Time'].mean(), new_md_df_intel['Comm.Time'].mean()]  # Sub-category for group 2
group2_sub2 = [new_md_leak_df_intel['Comp.Time'].mean(), new_md_df_intel['Comp.Time'].mean()]  # Sub-category for group 2

new_drone_leak_df_intel['Total'] = new_drone_leak_df_intel['Comm.Time'] + new_drone_leak_df_intel['Comp.Time']
new_drone_df_intel['Total'] = new_drone_df_intel['Comm.Time'] + new_drone_df_intel['Comp.Time']
new_md_leak_df_intel['Total'] = new_md_leak_df_intel['Comm.Time'] + new_md_leak_df_intel['Comp.Time']
new_md_df_intel['Total'] = new_md_df_intel['Comm.Time'] + new_md_df_intel['Comp.Time']
# Calculate the mean and the 95% confidence interval
mean = new_drone_leak_df_intel['Total'].mean()
std = new_drone_leak_df_intel['Total'].std()
n = len(new_drone_leak_df_intel['Total'])
ci = 1.96 * (std / np.sqrt(n))  # 95% CI is approximately 1.96 * SE

# Create a new DataFrame for mean and CI
df_drone_exec_leakmean = mean
df_drone_exec_leaklci = mean - ci
df_drone_exec_leakuci = mean + ci


# Calculate the mean and the 95% confidence interval
mean = new_drone_df_intel['Total'].mean()
std = new_drone_df_intel['Total'].std()
n = len(new_drone_df_intel['Total'])
ci = 1.96 * (std / np.sqrt(n))  # 95% CI is approximately 1.96 * SE

# Create a new DataFrame for mean and CI
df_drone_exec_mean = mean
df_drone_exec_lci = mean - ci
df_drone_exec_uci = mean + ci


mean = new_md_leak_df_intel['Total'].mean()
std = new_md_leak_df_intel['Total'].std()
n = len(new_md_leak_df_intel['Total'])
ci = 1.96 * (std / np.sqrt(n))  # 95% CI is approximately 1.96 * SE

# Create a new DataFrame for mean and CI
df_md_exec_leakmean = mean
df_md_exec_leaklci = mean - ci
df_md_exec_leakuci = mean + ci


# Calculate the mean and the 95% confidence interval
mean = new_md_df_intel['Total'].mean()
std = new_md_df_intel['Total'].std()
n = len(new_md_df_intel['Total'])
ci = 1.96 * (std / np.sqrt(n))  # 95% CI is approximately 1.96 * SE

# Create a new DataFrame for mean and CI
df_md_exec_mean = mean
df_md_exec_lci = mean - ci
df_md_exec_uci = mean + ci





conf_int1 = [df_drone_exec_leakuci-df_drone_exec_leaklci, df_drone_exec_uci-df_drone_exec_lci]
conf_int2 = [df_md_exec_leakuci-df_md_exec_leaklci, df_md_exec_uci-df_md_exec_lci]




# Set the number of groups and bar width
n_groups = len(labels)
bar_width = 0.2  # width of a single group

# Create the figure and axis
fig, ax = plt.subplots()

# Create the positions for each group
indices = np.arange(n_groups)
# Define colors for each bar
colors_group1_sub1 = 'darkgray'
colors_group1_sub2 = 'gray'
colors_group2_sub1 = 'darkgray'
colors_group2_sub2 = 'gray'
# Create first stacked bar for group 1
print(group1_sub1)
print(group1_sub2)
print(group2_sub1)
print(group2_sub2)
p1 = ax.bar(indices, group1_sub1, bar_width, label='Drone - Comm.Time', color=colors_group1_sub1)
p2 = ax.bar(indices, group1_sub2, bar_width, bottom=group1_sub1, label='Drone - Comp.Time',color=colors_group1_sub2, yerr=conf_int1, capsize=5)

# Create second stacked bar for group 2, offset by bar_width
p3 = ax.bar(indices + bar_width, group2_sub1, bar_width, label='WD - Comm.Time',color=colors_group2_sub1, hatch='\\')
p4 = ax.bar(indices + bar_width, group2_sub2, bar_width, bottom=group2_sub1, label='WD - Comp.Time', color=colors_group2_sub2, hatch='\\', yerr=conf_int2, capsize=5 )

# Add labels, title, and custom x-axis tick labels
ax.set_xlabel('Schemes',fontsize = 14)
ax.set_ylabel('Execution Time [ms]',fontsize = 14)
#ax.set_title('Grouped Stacked Bar Plot Example')
ax.set_xticks(indices + bar_width/ 2)
ax.set_xticklabels(labels,fontsize = 14)
ax.tick_params(axis='y', labelsize=14)
ax.legend(fontsize = 14)
ax.grid('on')
# Display the plot
plt.tight_layout()
plt.show()



df_client_ram_cheng,df_server_ram_cheng = fram.extractram('intelram',1000)
df_client_ram_leak,df_server_ram_leak = fram.extractram('leakintelram',1000)

df_client_ram_cheng['ram']= df_client_ram_cheng['ram']/1000
df_server_ram_cheng['ram']= df_server_ram_cheng['ram']/1000
df_client_ram_leak['ram']= df_client_ram_leak['ram']/1000
df_server_ram_leak['ram']= df_server_ram_leak['ram']/1000


mean = df_client_ram_cheng['ram'].mean()
std = df_client_ram_cheng['ram'].std()
n = len(df_client_ram_cheng['ram'])
ci = 1.96 * (std / np.sqrt(n))  # 95% CI is approximately 1.96 * SE

# Create a new DataFrame for mean and CI
df_client_ram_chengmean = mean
df_client_ram_chenglci = mean - ci
df_client_ram_chenguci = mean + ci




# Calculate the mean and the 95% confidence interval
mean = df_server_ram_cheng['ram'].mean()
std = df_server_ram_cheng['ram'].std()
n = len(df_server_ram_cheng['ram'])
ci = 1.96 * (std / np.sqrt(n))  # 95% CI is approximately 1.96 * SE

# Create a new DataFrame for mean and CI
df_server_ram_chengmean = mean
df_server_ram_chenglci = mean - ci
df_server_ram_chenguci = mean + ci


mean = df_client_ram_leak['ram'].mean()
std = df_client_ram_leak['ram'].std()
n = len(df_client_ram_leak['ram'])
ci = 1.96 * (std / np.sqrt(n))  # 95% CI is approximately 1.96 * SE

# Create a new DataFrame for mean and CI
df_client_ram_leakmean = mean
df_client_ram_leaklci = mean - ci
df_client_ram_leakuci = mean + ci




# Calculate the mean and the 95% confidence interval
mean = df_server_ram_leak['ram'].mean()
std = df_server_ram_leak['ram'].std()
n = len(df_server_ram_leak['ram'])
ci = 1.96 * (std / np.sqrt(n))  # 95% CI is approximately 1.96 * SE

# Create a new DataFrame for mean and CI
df_server_ram_leakmean = mean
df_server_ram_leaklci = mean - ci
df_server_ram_leakuci = mean + ci





labels = ['Obscura', 'Cheng et al.']

data1 = [df_server_ram_leakmean, df_server_ram_chengmean]
data2 = [df_client_ram_leakmean, df_client_ram_chengmean]
# Sample confidence intervals
conf_int1 = [df_server_ram_leakuci-df_server_ram_leaklci, df_server_ram_chenguci-df_server_ram_chenglci]
conf_int2 = [df_client_ram_leakuci-df_client_ram_leaklci, df_client_ram_chenguci-df_client_ram_chenglci]
# Set the number of groups and bar width
n_groups = len(labels)
bar_width = 0.2  # width of a single group

print(data1)
print(data2)

print(conf_int1)
print(conf_int2)

# Create the figure and axis
fig, ax = plt.subplots()

# Create the positions for each group
indices = np.arange(n_groups)
# Define colors for each bar
colors_group1_sub1 = 'gray'
#colors_group1_sub2 = 'lightgreen'
colors_group2_sub1 = 'darkgray'
#colors_group2_sub2 = 'orange'
# Create first stacked bar for group 1

p1 = ax.bar(indices, data1, bar_width, label='Drone', yerr=conf_int1,capsize=5, color=colors_group1_sub1 , alpha=0.7)
#p2 = ax.bar(indices, group1_sub2, bar_width, bottom=group1_sub1, label='Drone - Comp.Time',color=colors_group1_sub2)

# Create second stacked bar for group 2, offset by bar_width
p3 = ax.bar(indices + bar_width, data2, bar_width,  label='WD', yerr=conf_int2, capsize=5, color=colors_group2_sub1, alpha=0.7, hatch = '\\')
#p4 = ax.bar(indices + bar_width, group2_sub2, bar_width, bottom=group2_sub1, label='MD - Comp.Time', color=colors_group2_sub2)

# Add labels, title, and custom x-axis tick labels
ax.set_xlabel('Schemes',fontsize = 14)
ax.set_ylabel('RAM Consumption [Mbytes]',fontsize = 14)
#ax.set_title('Grouped Stacked Bar Plot Example')
ax.set_xticks(indices + bar_width/ 2)
ax.set_xticklabels(labels,fontsize = 14)
ax.tick_params(axis='y', labelsize=14)
ax.legend(loc=9,fontsize = 14)
ax.grid('on')
# Display the plot
plt.tight_layout()
plt.show()
