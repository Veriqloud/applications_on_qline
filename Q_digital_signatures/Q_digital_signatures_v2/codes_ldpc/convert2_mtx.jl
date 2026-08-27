using Test, SparseArrays
using LDPCStorage
using NPZ
using MatrixMarket

@testset "load hqqcsc.json" begin
    
    # read alist format
    # H_loaded = load_alist(file_path)
    # check it ? 
    # H_checked_redundancy = load_alist(file_path; check_redundant=true)
    # @test H_checked_redundancy == H_loaded
    # @test H == H_loaded
    # # check failures
    # @test_throws Exception load_alist("$(pkgdir(LDPCStorage))/test/files/test_Hqc.cscmat")  # completely invalid file

    path = length(ARGS) > 0 ? ARGS[1] : error("expect path in ARGS")
    # for qccsc only, corresponds to QCE in doc
    expansion_factor = length(ARGS) > 1 ? parse(Int, ARGS[2]) : 4
    print(path)
    print(expansion_factor)
    if occursin("qccsc", path) 
        Hqc = load_ldpc_from_json(path)
        H = LDPCStorage.Hqc_to_pcm(Hqc, expansion_factor) 
        path = replace(path, ".json" => ".mtx")
        
        mmwrite(path, H)

    end

end
