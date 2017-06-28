
###Git repository of java-assess framework is located in AFS::/p/swamp/gits/java-assess-master


###To clone the latest version from the java-assess repository:
###This would get the latest version of the java-assess into the ./java-assess-master
```sh
%% git clone <user-account>@<host-name>:/p/swamp/gits/java-assess-master
```


###To pull updates from the central repository 
```sh
%% git pull origin master
```


###To push updates from the central repository 
```sh
%% git push origin master
```


###To push tags 
```sh
%% git push origin --tags
```


###To create a release bundle (to MIR)
(
cd java-assess-master
 ./util/create_release_bundle.sh <destination directory> 
)


