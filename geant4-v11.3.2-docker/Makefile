build:
	sudo docker build -t geant4:v11.3.2 .

run:
	sudo docker run -d -it --name geant4_docker \
	-p 2223:22 \
	-v $(pwd)/work:/work \
	geant4

bash:
	sudo docker exec -it geant4_docker /bin/bash

ssh:
	ssh -p 2223 root@localhost

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
