FROM ubuntu:latest

# install python 3.11
RUN apt-get update && apt-get install -y python3.11 python3.11-pip

# install python packages
COPY requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

# copy the app
COPY . /app
WORKDIR /app

# run the app
CMD ["python3.11", "main.py"]
