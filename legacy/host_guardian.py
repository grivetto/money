import subprocess, time, logging

logging.basicConfig(filename='/home/marco/denaro/host_guardian.log', level=logging.INFO, format='%(asctime)s - SENTRY - %(message)s')

def get_containers():
    res = subprocess.run(['sudo', 'docker', 'ps', '-a', '--format', '{{.Names}}|{{.Status}}'], capture_output=True, text=True)
    return res.stdout.strip().split('\n')

def repair_container(name):
    logging.warning(f'Container {name} is unhealthy. Attempting repair...')
    # Get logs to diagnose
    logs = subprocess.run(['sudo', 'docker', 'logs', '--tail', '20', name], capture_output=True, text=True).stdout
    logging.info(f'Logs for {name}:\n{logs}')
    
    # Simple repair: Restart
    subprocess.run(['sudo', 'docker', 'restart', name])
    logging.info(f'Container {name} restarted.')

def main():
    logging.info('Sentry Host-Guardian started. Monitoring Docker fleet...')
    while True:
        containers = get_containers()
        for c in containers:
            if not c: continue
            name, status = c.split('|')
            if 'restarting' in status.lower() or 'exited' in status.lower():
                repair_container(name)
        time.sleep(60)

if __name__ == '__main__':
    main()
