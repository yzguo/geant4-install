build:
	sudo docker build -t geant4:v11.3.2 .

run:
	sudo docker run -d -it --name geant4_docker \
	-p 2223:22 \
	geant4:v11.3.2

bash:
	sudo docker exec -it geant4_docker /bin/bash

ssh:
	ssh -XY -p 2223 root@localhost

example:
	sudo docker exec -it geant4_docker /bin/bash -c "cd /work/geant4/share/Geant4/examples/basic/B1 && mkdir -p build && cd build && cmake .. && make && ./exampleB1"
	echo "Example B1 executed. Check the output for results."

stop:
	sudo docker stop geant4_docker

remove:
	sudo docker rm geant4_docker

save:
	sudo docker commit geant4_docker geant4_image
	sudo docker save -o geant4_image.tar geant4_image
	gzip -f geant4_image.tar

load:
	gunzip -f geant4_image.tar.gz
	sudo docker load -i geant4_image.tar
	sudo docker tag geant4_image geant4
