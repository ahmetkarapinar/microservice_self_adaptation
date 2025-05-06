from UPISAS.strategies.ramses_strategy import RamsesNovelStrategy
from UPISAS.strategies.ramses_baseline_strategy import RamsesBaselineStrategy 
from UPISAS.exemplar import Exemplar
from UPISAS.exemplars.swim import SWIM
from UPISAS.exemplars.ramses import RAMSES
import signal
import sys
import time

if __name__ == '__main__':
    
    exemplar = RAMSES(auto_start=True)
    time.sleep(5)
    exemplar.stop_existing_adaptation() # First stop existing adaptation mechanism in RAMSES itself.
    time.sleep(10)
    exemplar.stop_existing_adaptation() # First stop existing adaptation mechanism in RAMSES itself.

    try:
        strategy = RamsesNovelStrategy(exemplar)

        strategy.get_monitor_schema()
        strategy.get_adaptation_options_schema()
        strategy.get_execute_schema()

        while True:
            #input("Try to adapt?")
            strategy.monitor(with_validation=False, verbose=False)
            if strategy.analyze():
                if strategy.plan():
                    if strategy.execute(with_validation=False):
                        print("[Runner] Adaptation successfully made!")
                        #break
            time.sleep(5)
            
    except (Exception, KeyboardInterrupt) as e:
        print(str(e))
        input("something went wrong")
        #exemplar.stop_container()
        sys.exit(0)