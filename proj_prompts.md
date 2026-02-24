You are expert of coding assist me for the following task

1. this project will create a python library which used by other project that can install it with `pip install `
2. the goal of the project is to provide generic logging(json based) message and print to the STD, which when apps run in GKE, the logging message can be configured as the  log based metrics and later be consumed by Grafana
3. Review existing code in lib
4. it will need provide both metric messes of json based and Promethus format. prometus can be abled based on setting.
5. all default setting should be read from `.configs` or OS environment varaiables. OS environment variables takes the piority. Some mandatory settings must exist other wise thow errors when initilize the logger and stop the app running.
6. json logging format: pay attention, the caller can add extra custom field as needed. the following foramt are the fixed fileds for all callers
```json
  {
    "info": {    
    },
    "app_name": "sample app",
    "app_type": "shinyproxy_app, gke_job, gke_api and etc"
    "message": "App started",
    "counter": 1,
    "other custom field": "value"
  },


```
7. after you review the json format, you can provide suggestions for best fit.
8. you will generate code ,readme, and unit testsl.
9. generate a report of what you want to do and ask me if there is any questions.
10. after I don't have any questions, you generate a report of what you are going to do and wait for my confirm.
11. after my confiramtion 