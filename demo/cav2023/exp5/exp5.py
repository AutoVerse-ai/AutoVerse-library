from verse.agents.example_agent import CarAgent, NPCAgent
from verse.map import opendrive_map
from verse import Scenario
from verse.scenario import ScenarioConfig
from verse.plotter.plotter2D import *

import time
from enum import Enum, auto
import sys
import plotly.graph_objects as go


class LaneObjectMode(Enum):
    Vehicle = auto()
    Ped = auto()        # Pedestrians
    Sign = auto()       # Signs, stop signs, merge, yield etc.
    Signal = auto()     # Traffic lights
    Obstacle = auto()   # Static (to road/lane) obstacles


class AgentMode(Enum):
    Normal = auto()
    SwitchLeft = auto()
    SwitchRight = auto()
    Brake = auto()


class TrackMode(Enum):
    T0 = auto()
    T1 = auto()
    T2 = auto()
    M01 = auto()
    M12 = auto()
    M21 = auto()
    M10 = auto()


if __name__ == "__main__":
    input_code_name = './demo/tacas2023/exp5/example_controller5.py'    
    # config = 
    scenario = Scenario(ScenarioConfig(init_seg_length=1))
    scenario.add_agent(CarAgent('car1', file_name=input_code_name))
    scenario.add_agent(NPCAgent('car2'))
    scenario.add_agent(NPCAgent('car3'))
    tmp_map = opendrive_map('./demo/tacas2023/exp5/t1_triple.xodr')

    scenario.set_map(tmp_map)
    scenario.set_init(
        [
            [[134, 11.5, 0, 5.0], [136, 14.5, 0, 5.0]],
            [[179.5, 59.5, np.pi/2, 2.5], [180.5, 62.5, np.pi/2, 2.5]],
            [[124.5, 87.5, np.pi, 2.0], [125.5, 90.5, np.pi, 2.0]],

            # [[-65, -57.5, 0, 5.0], [-65, -57.5, 0, 5.0]],
            # [[15, -67.0, 0, 2.5], [15, -67.0, 0, 2.5]],
            # [[106, 18.0, 0, 2.0], [106, 18.0, 0, 2.0]],
        ],
        [
            (AgentMode.Normal, TrackMode.T1, ),
            (AgentMode.Normal, TrackMode.T1, ),
            (AgentMode.Normal, TrackMode.T2, ),
        ]
    )
    # scenario.config.init_seg_length = 5
    start_time = time.time()
    traces = scenario.verify(60, 0.1)  # traces.dump('./output1.json')
    run_time = time.time()-start_time
    traces.dump("./demo/tacas2023/exp5/output5.json")
    print({
        "#A": len(scenario.agent_dict),
        "A": "C",
        "Map": "M4",
        "postCont": "DryVR",
        "Noisy S": "No",
        "# Tr": len(traces.nodes),
        "Run Time": run_time,
    })
    # traces = AnalysisTree.load('./output5.json')
    if len(sys.argv)>1 and sys.argv[1]=='p':
        fig = go.Figure()
        fig = reachtube_tree(traces, tmp_map, fig, 1, 2, [1, 2], 'lines', 'trace')
        fig.show()
