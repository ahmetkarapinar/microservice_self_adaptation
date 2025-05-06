from UPISAS.strategy import Strategy
from abc import ABC, abstractmethod
import requests
import pprint
import datetime
from UPISAS.exceptions import EndpointNotReachable, ServerNotReachable
from UPISAS.knowledge import Knowledge
from UPISAS import validate_schema, get_response_for_get_request
import logging

class RamsesNovelStrategy(Strategy):

    def monitor(self, endpoint_suffix="monitor", with_validation=True, verbose=True):
        fresh_data = self._perform_get_request(endpoint_suffix)
        if(verbose): print("[Monitor]\tgot fresh_data: " + str(fresh_data))
        if with_validation:
            if(not self.knowledge.monitor_schema): self.get_monitor_schema()
            validate_schema(fresh_data, self.knowledge.monitor_schema)
        data = self.knowledge.monitored_data
        for key in list(fresh_data.keys()):
            if key not in data:
                data[key] = []
            data[key].append(fresh_data[key])
        #print("[Knowledge]\tdata monitored so far: " + str(self.knowledge.monitored_data))
        if not hasattr(self.knowledge, "time"):
            self.knowledge.time = datetime.datetime.now()

        return True

    def analyze(self):
        """
        Analyze monitored data to detect unhealthy instances based on health utility score,
        calculate average metrics for each service, and detect failed/unreachable instances.
        Reset monitored data at the end of the phase to prevent unnecessary growth.
        """
        monitored_data = self.knowledge.monitored_data
        failed_instances = []
        unhealthy_instances = []
        qos_history = {}
        service_avg_metrics = {}

        # Ensure self.knowledge.adapted_instances exists
        if not hasattr(self.knowledge, "adapted_instances"):
            self.knowledge.adapted_instances = set()

        

        # Weights for the health utility score
        w1, w2, w3 = 4, 1, 1

        # Threshold for health utility score
        health_utility_score_threshold = 70

        # Deduction thresholds for avgResponseTime
        response_time_deductions = {
            500: 5,
            1000: 10,
            1500: 15,
            2000: 20
        }

        for service_id, service_data_list in monitored_data.items():
            qos_history[service_id] = {}
            total_availability = 0
            total_response_time = 0
            total_health_utility_score = 0

            # Use a set to ensure unique instance IDs
            unique_instances = set()

            for service_data in service_data_list:  # Iterate through the list of service data
                for instance in service_data.get("snapshot", []):  # Access the 'snapshot' key
                    instance_id = instance.get("instanceId")

                    unique_instances.add(instance_id)

                    http_metrics = instance.get("httpMetrics", {})

                    # Initialize request counters
                    total_requests = 0
                    successful_requests = 0
                    successful_requests_duration = 0.0

                    # Iterate through OutcomeMetrics to calculate counts and durations
                    for endpoint, endpoint_metrics in http_metrics.items():
                        outcome_metrics = endpoint_metrics.get("outcomeMetrics", {})
                        success = outcome_metrics.get("SUCCESS", {}).get("count", 0)
                        server_error = outcome_metrics.get("SERVER_ERROR", {}).get("count", 0)
                        success_duration = outcome_metrics.get("SUCCESS", {}).get("totalDuration", 0.0)

                        successful_requests += success
                        successful_requests_duration += success_duration
                        total_requests += success + server_error

                    # Calculate availability (default to 1.0 if no requests)
                    availability = 1.0 if total_requests == 0 else successful_requests / total_requests

                    # Calculate average response time (default to 0 if no successful requests)
                    avg_response_time = 0.0 if successful_requests == 0 else successful_requests_duration / successful_requests

                    # Null-safe checks for CPU usage and disk space metrics
                    cpu_usage = instance.get("cpuUsage")
                    disk_total = instance.get("diskTotalSpace")
                    disk_free = instance.get("diskFreeSpace")

                    # Provide default values for null cases
                    if cpu_usage is None or cpu_usage < 0:
                        cpu_usage = 0.0  # Default to min usage
                    if disk_total is None or disk_total <= 0:
                        disk_total = 1.0  # Default total disk space
                    if disk_free is None:
                        disk_free = 1.0  # Default free disk space

                    # Calculate disk remaining percentage
                    disk_remaining_percentage = disk_free / disk_total

                    # Deduction based on avg response time
                    response_time_penalty = 0
                    for threshold, deduction in response_time_deductions.items():
                        if avg_response_time > threshold:
                            response_time_penalty = deduction

                    # Calculate health utility score
                    cpu_utility = 1 - cpu_usage  # Lower CPU usage is better

                    health_utility_score = ((w1 * availability + 
                                             w2 * cpu_utility + 
                                             w3 * disk_remaining_percentage) / 
                                             (w1 + w2 + w3) * 100) - response_time_penalty

                    # Update QoS history with health score and avg response time
                    qos_history[service_id][instance_id] = {
                        "availability": round(availability, 4),
                        "avgResponseTime": round(avg_response_time, 4),
                        "healthUtilityScore": round(health_utility_score, 4),
                        "cpuUsage": round(cpu_usage, 4),
                        "diskRemainingPercentage": round(disk_remaining_percentage, 4),
                        "total_requests": total_requests,
                        "successful_requests": successful_requests,
                        "successful_requests_duration": round(successful_requests_duration, 4),
                    }

                    # Accumulate metrics for service averages
                    total_availability += availability
                    total_response_time += avg_response_time
                    total_health_utility_score += health_utility_score

                    # Detect failed/unreachable instances
                    status = instance.get("status", "")
                    failed = instance.get("failed", False)
                    unreachable = instance.get("unreachable", False)

                    if status in ["FAILED", "UNREACHABLE"] or failed or unreachable and instance_id not in self.knowledge.adapted_instances:
                        failed_instances.append({
                            "service_id": service_id,
                            "instance_id": instance_id
                        })
                        self.knowledge.adapted_instances.add(instance_id)

                    # Check health utility score against the threshold
                    if health_utility_score < health_utility_score_threshold and instance_id not in self.knowledge.adapted_instances:
                        unhealthy_instances.append({
                            "service_id": service_id,
                            "instance_id": instance_id
                        })
                        self.knowledge.adapted_instances.add(instance_id)

            # Calculate average metrics for the service
            instance_count = len(unique_instances)
            elapsed_time_seconds = (datetime.datetime.now() - self.knowledge.time).total_seconds()  # Calculate elapsed time 
            elapsed_minutes = int(elapsed_time_seconds // 60)  # Get minutes
            elapsed_seconds = int(elapsed_time_seconds % 60)  # Get remaining seconds
            elapsed_time_formatted = f"{elapsed_minutes}m {elapsed_seconds}s"  # Format as 'Xm Ys'
            if instance_count > 0:
                service_avg_metrics[service_id] = {
                    "avgAvailability": round(total_availability / instance_count, 4),
                    "avgResponseTime": round(total_response_time / instance_count, 4),
                    "avgHealthUtilityScore": round(total_health_utility_score / instance_count, 4),
                    "instanceCount": instance_count,
                    "timestamp": elapsed_time_formatted  # Add the current timestamp
                }
            
        # Store analysis results in the knowledge base
        self.knowledge.analysis_data = {
            "failed_instances": failed_instances,
            "unhealthy_instances": unhealthy_instances,
            "qos_history": qos_history,
            "service_avg_metrics": service_avg_metrics
        }
        print("[ANALYZE] Updated QoS history, unhealthy instances, failed instances, and service averages: ", pprint.pformat(self.knowledge.analysis_data))

        # Reset monitored data
        self.knowledge.monitored_data = {}
        print("[ANALYZE] Monitored data reset.")

        if len(failed_instances) == 0 and len(unhealthy_instances) == 0:
            print("[ANALYZE] No need for adaptation...")
            return False
        return True




    def plan(self):
        """
        Plan adaptation actions for unhealthy instances and failed instances.
        """
        analysis_data = self.knowledge.analysis_data
        failed_instances = analysis_data.get("failed_instances", [])
        unhealthy_instances = analysis_data.get("unhealthy_instances", [])
        qos_history = analysis_data.get("qos_history", {})
        adaptation_plan = []
        adaptation_plan2 = []

        # Prepare the load balancer weight adjustments
        load_balancer_adjustments = []

        # # Add adaptation actions for each failed or unhealthy instance
        services_to_adapt = {entry["service_id"] for entry in failed_instances + unhealthy_instances}
        for service_id in services_to_adapt:
            service_id = service_id.lower()
            adaptation_plan.append({
                "operation": "addInstances",
                "serviceImplementationName": service_id,
                "numberOfInstances": 1  
            })

            # Adjust load balancer weights
            unhealthy_instances_in_service = []
            for instance in unhealthy_instances:
                if instance["service_id"].lower() == service_id.lower():
                    unhealthy_instances_in_service.append(instance)

            if len(unhealthy_instances_in_service) == 1:  # Only one unhealthy instance in the service
                unhealthy_instance = unhealthy_instances_in_service[0]
                instance_id = unhealthy_instance["instance_id"]

                # Health score of the unhealthy instance
                unhealthy_health_score = qos_history[service_id.upper()].get(instance_id, {}).get("healthUtilityScore", 100)
                new_instance_health_score = 100  # Assume new instance has perfect health

                # Calculate new weight for the unhealthy instance
                total_health_score = unhealthy_health_score + new_instance_health_score


                unhealthy_weight = round(unhealthy_health_score 
                                         / total_health_score, 2)
                new_instance_weight = round(new_instance_health_score 
                                            / total_health_score, 2)

                # Add load balancer adjustment for the service
                adaptation_plan.append({
                    "operation": "changeLBWeights",
                    "serviceID": service_id,
                    "newWeights": {
                        instance_id: unhealthy_weight,  # Weight for unhealthy instance
                    },
                    "instancesToRemoveWeightOf": []  # Optional: specify instances to exclude entirely
                })



        # Store the adaptation plan in the knowledge
        self.knowledge.plan_data = adaptation_plan
        print("[PLAN] Updated part of the knowledge: ", self.knowledge.plan_data)
        return len(adaptation_plan) > 0

    
    def execute(self, adaptation=None, endpoint_suffix="execute", with_validation=True):
        if not adaptation:
            adaptation = self.knowledge.plan_data
        #print("Execution mock")
        if not isinstance(adaptation, list):
            logging.error("Adaptation plan is not a list.")
            raise ValueError("Adaptation plan must be a list of adaptation actions.")
        
        #Since we are storing each action in adaptation list, we need to iterate over the list.
        for action in adaptation:
            if with_validation:
                if not self.knowledge.execute_schema:
                    self.get_execute_schema()
                validate_schema(action, self.knowledge.execute_schema)

            url = '/'.join([self.exemplar.base_endpoint, endpoint_suffix])
            response = requests.post(url, json=action)
            print(f"[Execute] Posted configuration: {action}")
            if response.status_code == 200:
                print(f"[Execute] Response status code: {response.status_code}")

            if response.status_code == 404:
                logging.error("Cannot execute adaptation on remote system, check that the execute endpoint exists.")
                raise EndpointNotReachable
        return True