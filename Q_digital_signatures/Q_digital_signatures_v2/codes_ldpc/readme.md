# Matrix conversion

to convert ```rate_0.33/block_1572864_proto_2x6_313422410401.qccsc.json``` to a mtx format, use:  
~~~
julia convert2_mtx.jl rate_0.33/block_1572864_proto_2x6_313422410401.qccsc.json 512
~~~
It will take some time.

to install julia see : https://julialang.org/downloads/


to install LDPCStorage with julia : 
~~~
julia> ]
(v1.9) pkg> add LDPCStorage
(v1.9) pkg> add NPZ
(v1.9) pkg> add MatrixMarket
~~~ 
or follow instruction here : https://github.com/XQP-Munich/LDPCStorage.jl
