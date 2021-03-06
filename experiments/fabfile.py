import os,logging,time,boto3, glob,subprocess,calendar,sys
from fabric.api import task,local,run,put,get,lcd,cd,sudo,env,puts
logging.basicConfig(level=logging.INFO,format='%(asctime)s %(name)-12s %(levelname)-8s %(message)s',datefmt='%m-%d %H:%M',filename='../logs/experiments.log',filemode='a')
AMI = 'ami-848f3d92'  # AMI
KeyName = 'C:\\fakepath\\cs5356'  # REPLACE WITH YOUR OWN
SecurityGroupId = 'sg-06a6b562'  # REPLACE WITH YOUR OWN
IAM_ROLE = {'Arn': 'arn:aws:iam::248089713624:instance-profile/chdeploy',}   # REPLACE WITH YOUR OWN (Provide S3 access to allow backups)
KEY_FILE = "~/.ssh/cs5356" # REPLACE WITH YOUR OWN


env.user = "ubuntu" # DONT CHANGE
try:
    ec2_HOST = file("host").read().strip()
    env.hosts = [ec2_HOST,]
except:
    ec2_HOST = ""
    logging.warning("No host file available assuming that the instance is no launched")
    pass

env.key_filename = KEY_FILE


def get_status(ec2,spot_request_id):
    """
    Get status of EC2 spot request
    :param ec2:
    :param spot_request_id:
    :return:
    """
    current = ec2.describe_spot_instance_requests(SpotInstanceRequestIds=[spot_request_id,])
    instance_id = current[u'SpotInstanceRequests'][0][u'InstanceId'] if u'InstanceId' in current[u'SpotInstanceRequests'][0] else None
    return instance_id


@task
def launch_spot():
    """
    A helper script to launch a spot P2 instance running Deep Video Analytics
    To use this please change the keyname, security group and IAM roles at the top
    :return:
    """
    ec2 = boto3.client('ec2')
    ec2r = boto3.resource('ec2')
    ec2spec = dict(ImageId=AMI,
                   KeyName = KeyName,
                   SecurityGroupIds = [SecurityGroupId, ],
                   InstanceType = "p2.xlarge",
                   Monitoring = {'Enabled': True,},
                   IamInstanceProfile = IAM_ROLE)
    output = ec2.request_spot_instances(DryRun=False,
                                        SpotPrice="0.4",
                                        InstanceCount=1,
                                        LaunchSpecification = ec2spec)
    spot_request_id = output[u'SpotInstanceRequests'][0][u'SpotInstanceRequestId']
    logging.info("instance requested")
    time.sleep(30)
    waiter = ec2.get_waiter('spot_instance_request_fulfilled')
    waiter.wait(SpotInstanceRequestIds=[spot_request_id,])
    instance_id = get_status(ec2, spot_request_id)
    while instance_id is None:
        time.sleep(30)
        instance_id = get_status(ec2,spot_request_id)
    instance = ec2r.Instance(instance_id)
    with open("host",'w') as out:
        out.write(instance.public_ip_address)
    logging.info("instance allocated")
    time.sleep(10) # wait while the instance starts
    env.hosts = [instance.public_ip_address,]
    fh = open("connect.sh", 'w')
    fh.write("#!/bin/bash\n" + "ssh -i " + env.key_filename + " " + env.user + "@" + env.hosts[0] + "\n")
    fh.close()
    local("fab deploy_ec2") # this forces fab to set new env.hosts correctly


@task
def deploy_ec2(compose_file="docker-compose-gpu.yml"):
    """
    deploys code on hostname
    :return:
    """
    import webbrowser
    for attempt in range(3):
        try:
            run('ls')  # just run some command that has no effect to ensure you dont get timed out
            break  # break if you succeed
        except:
            time.sleep(30)  # on error wait 30 seconds
            pass
    with cd('deepvideoanalytics'):
        run('git pull')
        with cd("docker"):
            run('./rebuild_gpu.sh && nvidia-docker-compose -f {} up -d'.format(compose_file))
    if sys.platform == 'darwin':
        chrome_path = 'open -a /Applications/Google\ Chrome.app %s'
        webbrowser.get(chrome_path).open('http://{}:8000'.format(env.hosts[0]))