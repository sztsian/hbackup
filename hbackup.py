#!/usr/bin/python3

import socket
import sys
import os
import datetime
import time
import urllib.parse
import hashlib
import argparse

debug = False
haserror = False
total_files = total_dirs = total_links = total_file_len = upload_file_len = 0


def md5sum(filename, blocksize=1024 * 1024):
    hash = hashlib.md5()
    with open(filename, "rb") as f:
        for block in iter(lambda: f.read(blocksize), b""):
            hash.update(block)
    return hash.hexdigest()


def end_hbackup(retcode=0):
    s.send('END\n'.encode())
    data = s.recv(100).decode()
    print('S', data, end='')
    print('FDL: %d/%d/%d U/A: %d/%d' % (total_files, total_dirs, total_links,
                                        upload_file_len, total_file_len))
    if haserror:
        print("Encountered error when backuping file")
        print("Error msg append to " + err_log + ", please check it")
    sys.exit(retcode)


def send_dir(remote_name):
    global total_dirs
    total_dirs += 1
    s.send(('MKDIR ' + urllib.parse.quote(remote_name) + '\n').encode())
    data = s.recv(100).decode()
    if data[0:2] == 'OK':
        print("")
        if debug:
            print('S', data, end='')
        return
    print(' S', data, end='')
    log_err(remote_name + ' ' + data)


def send_link(remote_name, linkto):
    global total_links
    total_links += 1
    s.send(('MKLINK ' + urllib.parse.quote(remote_name) + ' ' +
            urllib.parse.quote(linkto) + '\n').encode())
    data = s.recv(100).decode()
    if data[0:2] == 'OK':
        print("")
        if debug:
            print('S', data, end='')
        return
    print(' S', data, end='')
    log_err(remote_name + ' ' + data)


def send_file(local_file_name, remote_name):
    global total_files, total_file_len, upload_file_len
    total_files += 1
    filemd5sum = md5sum(local_file_name)
    file_size = os.path.getsize(local_file_name)
    total_file_len += file_size
    if debug:
        print(filemd5sum + "_" + str(file_size))
    s.send(('FILE ' + filemd5sum + ' ' + str(file_size) + ' ' +
            urllib.parse.quote(remote_name) + '\n').encode())
    data = s.recv(100).decode()
    if data[0:2] == 'OK':
        if debug:
            print('S', data, end='')
        print("")
        return
    if data[0:5] == 'ERROR':
        print(' S', data, end='')
        log_err(local_file_name + ' --> ' + remote_name + ' ' + data)
        return
    if data[0:4] == 'DATA':
        if debug:
            print('S', data, end='')
            print('I will send file')
        CHUNKSIZE = 1024 * 1024
        file = open(local_file_name, "rb")
        bytes_send = 0
        try:
            while True:
                need_read = file_size - bytes_send
                if need_read > 0:
                    if need_read > CHUNKSIZE:
                        bytes_read = file.read(CHUNKSIZE)
                    else:
                        bytes_read = file.read(need_read)
                    if len(bytes_read) > 0:
                        upload_file_len += len(bytes_read)
                        s.send(bytes_read)
                        bytes_send += len(bytes_read)
                    else:
                        break
                else:
                    break
        finally:
            file.close()
        data = s.recv(100).decode()
        if data[0:2] == 'OK':
            if debug:
                print('S', data, end='')
            print("")
            return
    print('S', data, end='')
    end_hbackup(-1)


def log_err(msg):
    global haserror
    haserror = True
    if err_log == "":
        print(msg)
        exit(-1)
    f = open(err_log, 'a')
    now = datetime.datetime.now()
    f.write(str(now) + ' ' + msg)
    f.close()


parser = argparse.ArgumentParser(description='hbackup')
parser.add_argument(dest='hostname', metavar='HostName')
parser.add_argument(dest='port', metavar='TcpPort', type=int)
parser.add_argument(dest='password', metavar='Password')
parser.add_argument(dest='file_name', metavar='File/DirToSend')
parser.add_argument(dest='remote_name', metavar='RemoteName', nargs='?')
parser.add_argument('-d', dest='debug', action='store_true', help='debug mode')
parser.add_argument(
    '-e',
    dest='err_log',
    metavar='err_log_file',
    action='store',
    help='error msg will be append to err_log_file, and continue to run')
args = parser.parse_args()
err_log = args.err_log
debug = args.debug
host = args.hostname
port = args.port
pass_word = args.password
file_name = args.file_name
if args.remote_name == None:
    file_new_name = file_name
else:
    file_new_name = args.remote_name

try:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
except socket.error:
    print('Failed to creat socket.')
    sys.exit(-1)
try:
    host_ip = socket.gethostbyname(host)
except socket.gaierror:
    print('Host name could not be resolved. Exiting...')
    sys.exit(-1)

try:
    s.connect((host_ip, port))
except socket.error:
    if s:
        s.close()
    print('Socket connection is not established!\t' + message)
    sys.exit(1)
if debug:
    print('Connected to ' + host + ' on IP ' + host_ip + ' port ' + str(port) +
          '.')

s.send(('PASS ' + pass_word + '\n').encode())
data = s.recv(100).decode()
if data[0:2] != 'OK':
    if debug:
        print('S', data, end='')
    sys.exit(-1)

if os.path.islink(file_name):
    print(file_name + " is symlink", end='')
    linkto = os.readlink(file_name)
    send_link(file_new_name, linkto)
    end_hbackup()

if os.path.isfile(file_name):
    print(file_name + " is file", end='')
    send_file(file_name, file_new_name)
    end_hbackup()

if not os.path.isdir(file_name):
    print(file_name + " is not symlink, file, dir, I do not know how to deal")
    end_hbackup()

print(file_name + " is dir")

for root, dirs, files in os.walk(file_name, topdown=True):
    for name in files:
        local_file_name = os.path.join(root, name)
        remote_file_name = file_new_name + '/' + root[len(file_name) +
                                                      1:] + '/' + name
        if os.sep == "\\":
            remote_file_name = remote_file_name.replace("\\", "/")
        if debug:
            print("F root=" + root + " name=" + name + " file_new_name=" +
                  file_new_name)
            print(local_file_name + " --> " + remote_file_name)
        if os.path.islink(local_file_name):
            print(local_file_name + " is symlink", end='')
            linkto = os.readlink(local_file_name)
            send_link(remote_file_name, linkto)
        elif os.path.isfile(local_file_name):
            print(local_file_name, end='')
            if debug:
                print(" is file")
            send_file(local_file_name, remote_file_name)
        else:
            print(local_file_name, " SKIP")

    for name in dirs:
        local_file_name = os.path.join(root, name)
        remote_file_name = file_new_name + '/' + root[len(file_name) +
                                                      1:] + '/' + name
        if os.path.islink(local_file_name):
            print(local_file_name + " is symlink", end='')
            linkto = os.readlink(local_file_name)
            send_link(remote_file_name, linkto)
            continue
        print(os.path.join(root, name) + " is dir", end='')
        if os.sep == "\\":
            remote_file_name = remote_file_name.replace("\\", "/")
        send_dir(remote_file_name)

end_hbackup()
