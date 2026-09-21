# Pseudocode for the algorithm

Function Scan(sender, coordinates):
Gives a heatmap structure of network coverage from a coordinate and pecific sender

Function Evaluate(coordinates):
Evaluates the level of cover and possibilities of assistance of a given location

## Input:

Number of relay senders

Minimum starting distance away from the target.

Maximum time to complete mission.

Location of supply unit.

Enemy locations

## Algorithm

0. (zero relay points)

Place sender on target location, run Scan(sender)

Given the coverage map from scan find potential starting locations on the roads. Starting position has to be outside minimum starting distance away from target. Only consider roads. If outside, take closest point the goal with coverage. Only consider points with coverage. 

For each proposed point, find the best path to target. Then Evaluate(position) for each start position.

Output 3 or set amount of starting locations with their paths

1. (n-relay senders)

Run the 0 sender algotirhm with Scan(relay sender).

For each starting location gained from this rerun the same step with the starting locations as goals. Repeat until outside of cover radius while within number of relay senders

## Output

A list of possible start position, each with their evaluation on why they are good. Each with the road we are supposed to take, how many relay senders it will cost and the time it will take.