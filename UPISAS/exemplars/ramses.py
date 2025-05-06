from UPISAS.exemplar import Exemplar
import requests

class RAMSES(Exemplar):
    """
    A class which encapsulates a self-adaptive exemplar run in a docker container.
    """
    def __init__(self, auto_start = False):

        # This docker particularly for running Scenario 1.
        ramses_docker_kwargs = {
            "name":  "ramses-scenario-restclient",
            "image": "ahmetkarapinar/scenario5:latest", # image of newly created scenario.
            "network": "ramses-sas-net" # IMPORTANT -> Network should be same with Ramses's network.
            } 
        
        # The url should be same with  
        #super().__init__("http://127.0.0.1:50000", auto_start)
        super().__init__("http://127.0.0.1:50000", ramses_docker_kwargs, auto_start)

    def stop_existing_adaptation(self):

        # IMPORTANT -> 32785 port must be same with "ramses-dashboard"'s port number
        url = "http://localhost:32785/configuration/stopAdaptation"
        response = requests.post(
            url,
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Content-Type": "application/x-www-form-urlencoded",
            }
        )
        print(f"[Stop Adaptation] Stopping adaptation... \n[Start Run] Response: {response.status_code}")

    def start_run(self):
        # We assume that RAMSES Interface and RAMSES itself are already running...
        pass