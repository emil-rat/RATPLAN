Context document to describe the overarching goal of the task.

The end goal is a mission planner that tells a group where to operate from, what path to drive the rat and where t place its relay nodes.\\

For the connectivity module a first approach is to just use ITWOM for connectivity approximation, I believe we can do better. We use ITWOM as a prior and then with regular bayesian statistics and kriging we update the connectivity distribution live when we drive the rat. The hope is that this will get around the problem that ITWOM is not that good for our terrain and scale\\

For the mission planner a first approach is to use a road network 

