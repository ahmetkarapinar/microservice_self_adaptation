from UPISAS.strategy import Strategy
from abc import ABC, abstractmethod
import requests
import pprint
import datetime
from UPISAS.exceptions import EndpointNotReachable, ServerNotReachable
from UPISAS.knowledge import Knowledge
from UPISAS import validate_schema, get_response_for_get_request
import logging

class RamsesBaselineStrategy(Strategy):

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
        if not hasattr(self.knowledge, "time"):
            self.knowledge.time = datetime.datetime.now()
        #print("[Knowledge]\tdata monitored so far: " + str(self.knowledge.monitored_data))
        return True

    def analyze(self):
        """
        Analyze monitored data to detect failed/unreachable instances,
        calculate avgResponseTime and availability for each instance,
        and average metrics for each service. Resets monitored data at the end.
        """
        monitored_data = self.knowledge.monitored_data
        failed_instances = []
        qos_history = {}
        service_avg_metrics = {}

        for service_id, service_data_list in monitored_data.items():
            qos_history[service_id] = {}
            total_availability = 0
            total_response_time = 0
            instance_count = 0

            for service_data in service_data_list:  # Iterate through the list of service data
                for instance in service_data.get("snapshot", []):  # Access the 'snapshot' key
                    instance_id = instance.get("instanceId")

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

                    # Update QoS history with availability and avg response time
                    qos_history[service_id][instance_id] = {
                        "availability": round(availability, 4),
                        "avgResponseTime": round(avg_response_time, 4),
                        "total_requests": total_requests,
                        "successful_requests": successful_requests,
                        "successful_requests_duration": round(successful_requests_duration, 4),
                    }

                    # Accumulate metrics for service averages
                    total_availability += availability
                    total_response_time += avg_response_time
                    instance_count += 1

                    # Detect failed/unreachable instances
                    status = instance.get("status", "")
                    failed = instance.get("failed", False)
                    unreachable = instance.get("unreachable", False)

                    if status in ["FAILED", "UNREACHABLE"] or failed or unreachable:
                        failed_instances.append({
                            "service_id": service_id,
                            "instance_id": instance_id
                        })

            # Calculate average metrics for the service
            if instance_count > 0:
                elapsed_time_seconds = (datetime.datetime.now() - self.knowledge.time).total_seconds()  # Calculate elapsed time 
                elapsed_minutes = int(elapsed_time_seconds // 60)  # Get minutes
                elapsed_seconds = int(elapsed_time_seconds % 60)  # Get remaining seconds
                elapsed_time_formatted = f"{elapsed_minutes}m {elapsed_seconds}s"  # Format as 'Xm Ys'
                service_avg_metrics[service_id] = {
                    "avgAvailability": round(total_availability / instance_count, 4),
                    "avgResponseTime": round(total_response_time / instance_count, 4),
                    "instanceCount": instance_count,
                    "time": elapsed_time_formatted
                }

        # Store analysis results in the knowledge base
        self.knowledge.analysis_data = {
            "failed_instances": failed_instances,
            "qos_history": qos_history,
            "service_avg_metrics": service_avg_metrics
        }

        # Reset monitored data
        self.knowledge.monitored_data = {}
        print("[ANALYZE] Updated QoS history, failed instances, and service averages: ", pprint.pformat(self.knowledge.analysis_data))

        if len(failed_instances) == 0:
            print("[ANALYZE] No need for adaptation...")
            return False
        return True

    def plan(self):
        """
        Plan adaptation actions to handle failed or unreachable instances.
        """
        analysis_data = self.knowledge.analysis_data
        failed_instances = analysis_data.get("failed_instances", [])
        adaptation_plan = []

        # Add adaptation actions for each failed instance
        services_with_failures = {entry["service_id"] for entry in failed_instances}
        for service_id in services_with_failures:
            service_id = service_id.lower()
            adaptation_plan.append({
                "operation": "addInstances",
                "serviceImplementationName": service_id,
                "numberOfInstances": 1  # Start one new instance per service with failures
            })

        # Store the adaptation plan in the knowledge
        self.knowledge.plan_data = adaptation_plan
        print("[PLAN] Updated part of the knowledge: ", self.knowledge.plan_data)
        return len(adaptation_plan) > 0
    
    def execute(self, adaptation=None, endpoint_suffix="execute", with_validation=True):
        if not adaptation:
            adaptation = self.knowledge.plan_data

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
            print(f"[Execute] Response status code: {response.status_code}")

            if response.status_code == 404:
                logging.error("Cannot execute adaptation on remote system, check that the execute endpoint exists.")
                raise EndpointNotReachable
        return True