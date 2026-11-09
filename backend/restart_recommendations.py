#!/usr/bin/env python3
"""Restart only the recommendation relay recorded by this project, from Terminal."""
import json,os,signal,subprocess,sys,time,urllib.request
from pathlib import Path

def main():
    repo=Path(__file__).resolve().parent.parent;root=repo.parent/'private-imports/amazon';pidfile=root/'relay-background.pid'
    listener=subprocess.run(['lsof','-tiTCP:8772','-sTCP:LISTEN'],capture_output=True,text=True).stdout.strip()
    if listener:
        if not pidfile.exists() or listener!=pidfile.read_text().strip():raise SystemExit('Port 8772 belongs to another process; it was left running.')
        os.kill(int(listener),signal.SIGTERM)
        for _ in range(30):
            if subprocess.run(['lsof','-tiTCP:8772','-sTCP:LISTEN'],capture_output=True,text=True).returncode:break
            time.sleep(.1)
        else:raise SystemExit('Old relay has not stopped; no second relay was launched.')
    with (root/'relay-background.log').open('ab') as log:
        proc=subprocess.Popen([sys.executable,str(repo/'backend/relay.py'),'--data',str(root/'personalized'),'--db',str(root/'staged/amazon_history.sqlite'),'--tv-ip','192.168.1.36'],stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
    pidfile.write_text(str(proc.pid))
    for _ in range(30):
        if proc.poll() is not None:raise SystemExit('Relay did not start; see relay-background.log.')
        try:
            with urllib.request.urlopen('http://127.0.0.1:8772/recommendations',timeout=10) as response:data=json.load(response)
            if data.get('profiles'):print('Ready: '+str(len(data['profiles']))+' recommendation profiles, including the unassigned household.');return
        except (OSError,ValueError):time.sleep(.2)
    raise SystemExit('Relay started but readiness is not confirmed. Check relay-background.log.')
if __name__=='__main__':main()
