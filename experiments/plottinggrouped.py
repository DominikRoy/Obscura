import numpy as np
import matplotlib.pyplot as plt

# Sample data
labels = ['Group 1', 'Group 2', 'Group 3']
data1 = [20, 35, 30]
data2 = [25, 32, 34]
# Sample confidence intervals
conf_int1 = [3, 5, 4]
conf_int2 = [4, 2, 5]

# Number of groups
num_groups = len(labels)

# Set the bar width
bar_width = 0.35

# Create a range for the x locations of the groups
x = np.arange(num_groups)

# Create the figure and axis
fig, ax = plt.subplots()

# Create bars for the first group
bars1 = ax.bar(x - bar_width/2, data1, bar_width, label='Data 1', yerr=conf_int1, capsize=5, color='b', alpha=0.7)
# Create bars for the second group
bars2 = ax.bar(x + bar_width/2, data2, bar_width, label='Data 2', yerr=conf_int2, capsize=5, color='r', alpha=0.7)

# Add some text for labels, title, and custom x-axis tick labels, etc.
ax.set_xlabel('Groups')
ax.set_ylabel('Values')
ax.set_title('Grouped Bar Plot with Confidence Intervals')
ax.set_xticks(x)
ax.set_xticklabels(labels)
ax.legend()

# Show the plot
plt.tight_layout()
plt.show()
