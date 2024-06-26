import numpy as np
import os, sys
import matplotlib.pyplot as plt
import healpy as hp

#=================================================================================
# DEFINE A PATH FOR scratch data
# The data are storred using a default nside to minimize the needed storage
#=================================================================================
#python hwst_foscat_v2.py EE0256 /export/home/jmdeloui/heal_cnn/ /home1/scratch/jmdeloui/heal_cnn/ N
if len(sys.argv)<5:
    print('\nhwst_foscat usage:\n')
    print('python hwst_foscat <in> <scratch_path> <out> <cov>')
    print('============================================')
    print('<in>           : name of the 3 input data files: <in>_MONO.npy,<in>_HM1_MONO.npy,<in>_HM2_MONO.npy')
    print('<scratch_path> : name of the directory with all the input files (noise, TT,etc.) and also use for FOSCAT temporary files')
    print('<out>          : name of the directory where the computed data are stored')
    print('<nside>        : nside of the synthesised map')
    print('<cov>          : if Y use scat_cov istead of scat')
    print('<kernelsz>     : kernelsz of the convolution')
    print('============================================')
    exit(0)

scratch_path = sys.argv[2]
datapath = scratch_path
outpath = sys.argv[3]
nout      = int(sys.argv[4])
docov     = (sys.argv[5]=='Y')
kernelsz  = int(sys.argv[6])

dtype='float32'

test_mpi=False
for ienv in os.environ:
    if 'OMPI_' in ienv:
        test_mpi=True
    if 'PMI_' in ienv:
        test_mpi=True
        
if test_mpi:
    from mpi4py import MPI

    comm = MPI.COMM_WORLD
    size = comm.Get_size()
    rank = comm.Get_rank()
    if size>1:
        print('Use mpi facilities',rank,size)
    isMPI=True
else:
    size=1
    rank=0
    isMPI=False
    
#set the nside of input data
Default_nside=256

#=================================================================================
# DEFINE THE WORKING NSIDE
#=================================================================================

# set the default name
if kernelsz==5:
    outname='FOCUS_5x5%s%d'%(sys.argv[1],nout)
else:
    outname='FOCUS%s%d'%(sys.argv[1],nout)

if kernelsz==3:
    lam=1.2
else:
    lam=1.0

#=================================================================================
# Function to reduce the data used in the FoCUS algorithm 
#=================================================================================
def dodown(a,nout):
    nin=int(np.sqrt(a.shape[0]//12))
    if nin==nout:
        return(a)
    return(np.mean(a.reshape(12*nout*nout,(nin//nout)**2),1))

#=================================================================================
# Get data
#=================================================================================

# define the level of noise of the simulation
ampnoise=0.4
# coeficient to control bias iteration
Alpha=1.0
DAlpha=1.0

#number of simulations used as reference
nsim=100

#work with angle invariant statistics 
avg_ang=False

# Read data from disk
try:
    di=np.load(outpath+'/%sdi.npy'%(outname)) 
    d1=np.load(outpath+'/%sd1.npy'%(outname)) 
    d2=np.load(outpath+'/%sd2.npy'%(outname)) 
    td=np.load(outpath+'/%std.npy'%(outname))
    
except:
    td=dodown(np.load(datapath+'TT857_%d.npy'%(Default_nside)),nout)
    di=dodown(np.load(datapath+'%s_MONO.npy'%(sys.argv[1])),nout)
    d1=dodown(np.load(datapath+'%s_HM1_MONO.npy'%(sys.argv[1])),nout)
    d2=dodown(np.load(datapath+'%s_HM2_MONO.npy'%(sys.argv[1])),nout)

    if rank==0:
        np.save(outpath+'/%std.npy'%(outname),td)
        np.save(outpath+'/%sdi.npy'%(outname),di)
        np.save(outpath+'/%sd1.npy'%(outname),d1)
        np.save(outpath+'/%sd2.npy'%(outname),d2)
    
    if test_mpi:
        comm.Barrier()
        
    td=np.load(outpath+'/%std.npy'%(outname)) 
    di=np.load(outpath+'/%sdi.npy'%(outname)) 
    d1=np.load(outpath+'/%sd1.npy'%(outname)) 
    d2=np.load(outpath+'/%sd2.npy'%(outname)) 


# All information of the map is used
nin=Default_nside

tab=['MASK_GAL11_%d.npy'%(nin),'MASK_GAL09_%d.npy'%(nin),'MASK_GAL08_%d.npy'%(nin),'MASK_GAL06_%d.npy'%(nin),'MASK_GAL04_%d.npy'%(nin)]
mask=np.ones([len(tab),12*nout**2])
for i in range(len(tab)):
    mask[i,:]=dodown(np.load(datapath+tab[i]),nout)

#set the first mask to 1
mask[0,:]=1.0
for i in range(1,len(tab)):
    mask[i,:]=mask[i,:]*mask[0,:].sum()/mask[i,:].sum()
    
off=np.median(di[di>-1E10])
d1[di<-1E10]=off
d2[di<-1E10]=off
di[di<-1E10]=off

#=============================================

# compute amplitude to normalize the dynamic range
ampmap=1/dodown(np.load(scratch_path+'%s_NOISE%03d_full.npy'%(sys.argv[1][0:6],0)).flatten(),nout).std()

print('AMPMAP ',ampmap,off)

# rescale maps to ease the convergence
d1=ampmap*(d1-off)
d2=ampmap*(d2-off)
di=ampmap*(di-off)
td=ampmap*(td)

#compute all noise map statistics
noise=np.zeros([nsim,12*nout*nout],dtype=dtype)
noise1=np.zeros([nsim,12*nout*nout],dtype=dtype)
noise2=np.zeros([nsim,12*nout*nout],dtype=dtype)
for i in range(nsim):
    noise[i] =ampmap*dodown(np.load(scratch_path+'%s_NOISE%03d_full.npy'%(sys.argv[1][0:6],i)).flatten(),nout)
    noise1[i]=ampmap*dodown(np.load(scratch_path+'%s_NOISE%03d_hm1.npy'%(sys.argv[1][0:6],i)).flatten(),nout)
    noise2[i]=ampmap*dodown(np.load(scratch_path+'%s_NOISE%03d_hm2.npy'%(sys.argv[1][0:6],i)).flatten(),nout)

for i in range(nsim):
    noise1[i]-=np.mean(noise[i])
    noise2[i]-=np.mean(noise[i])
    noise[i] -=np.mean(noise[i])

sig_noise=1/(np.mean(noise**2,0))

if docov:
    import foscat.scat_cov as sc
else:
    import foscat.scat as sc
    
import foscat.Synthesis as synthe

if isMPI:
    scat_op=sc.funct(NORIENT=4,   # define the number of wavelet orientation
                     KERNELSZ=kernelsz,  # define the kernel size (here 5x5)
                     OSTEP=-1,     # get very large scale (nside=1)
                     LAMBDA=lam,
                     all_type=dtype,
                     TEMPLATE_PATH=scratch_path,
                     use_R_format=True,
                     isMPI=True,
                     mpi_rank=rank,
                     mpi_size=size)
else:
    scat_op=sc.funct(NORIENT=4,   # define the number of wavelet orientation
                     KERNELSZ=kernelsz,  # define the kernel size (here 5x5)
                     OSTEP=-1,     # get very large scale (nside=1)
                     LAMBDA=lam,
                     all_type=dtype,
                     TEMPLATE_PATH=scratch_path,
                     use_R_format=True)

if rank==0 or rank==2 or size==1:
    #compute d1xd2
    refH=scat_op.eval(d1,image2=d2,Auto=True,mask=mask)

if rank==1 or size==1:
    #compute Tdxdi
    refX=scat_op.eval(td,image2=di,Auto=False,mask=mask)

initb1=None
initb2=None
initb3=None

def loss_fct1(x,scat,args):

    ref  = args[0]
    mask = args[1]
    isig = args[2]
    p00  = args[3]
    
    b=scat.eval(x,image2=x,mask=mask,Auto=True)
    
    if p00==True:
        l_val=scat.bk_reduce_sum(scat.bk_abs(isig.P00*scat.bk_square(scat.bk_abs(ref.P00-b.P00))))
    else:
        l_val=scat.reduce_sum(scat.reduce_mean(isig*scat.square(ref-b)))

    return(l_val)

def loss_fct2(x,scat,args):

    ref  = args[0]
    TT   = args[1]
    mask = args[2]
    isig = args[3]
    p00  = args[4]
    
    b=scat.eval(TT,image2=x,mask=mask,Auto=False)
    if p00==True:
        l_val=scat.bk_reduce_sum(scat.bk_abs(isig.P00*scat.bk_square(scat.bk_abs(ref.P00-b.P00))))
    else:
        l_val=scat.reduce_sum(scat.reduce_mean(isig*scat.square(ref-b)))
    if docov:
        return(l_val*1E-5)
    else:
        return(l_val)

def loss_fct3(x,scat,args):

    ref  = args[0]
    im   = args[1]
    bias = args[2]
    mask = args[3]
    isig = args[4]
    p00  = args[5]

    
    a=scat.eval(im,image2=x,mask=mask,Auto=True)-bias
    
    if p00==True:
        l_val=scat.bk_reduce_sum(scat.bk_abs(isig.P00*scat.bk_square(scat.bk_abs(ref.P00-a.P00))))
    else:
        l_val=scat.reduce_sum(scat.reduce_mean(isig*scat.square(a-ref)))

    return(l_val)

def loss_fct4(x,scat,args):

    im   = scat.to_R_center(args[0])
    nsig = scat.to_R_center(args[1])
    
    l_val=100*scat.bk_square(scat.bk_reduce_mean(nsig*scat.bk_square(im-x))-1)
    
    return(l_val)

i1=d1
i2=d2
imap=di
init_map=((d1+d2)/2).astype(dtype)

for itt in range(5):

    if rank==0 or rank==2 or size==1:
        stat1 =scat_op.eval(i1,image2=i2,mask=mask,Auto=True)
        
        #loss1 : d1xd2 = (u+n1)x(u+n2)
        stat1_p_noise=scat_op.eval(i1+noise1[0],image2=i2+noise2[0],mask=mask,Auto=True)
        
        #bias1 = mean(F((d1+n1)*(d2+n2))-F(d1*d2))
        bias1 = stat1_p_noise-stat1
        isig1 = scat_op.square(stat1_p_noise-stat1)
        for k in range(1,nsim):
            stat1_p_noise=scat_op.eval(i1+noise1[k],image2=i2+noise2[k],mask=mask,Auto=True)
            bias1 = bias1 + stat1_p_noise-stat1
            isig1 = isig1 + scat_op.square(stat1_p_noise-stat1)

        bias1=bias1/nsim
        isig1=isig1/nsim-scat_op.square(bias1)
        isig1=1/isig1
        #bias1.reset_P00()
    
    if rank==1 or size==1:
        #loss2 : Txd = Tx(u+n)
        #bias2 = mean(F((T*(d+n))-F(T*d))
        stat2_p_noise=scat_op.eval(td,image2=imap+noise[0],mask=mask,Auto=False)
        stat2 =scat_op.eval(td,image2=imap,mask=mask,Auto=False)
        
        bias2 = stat2_p_noise-stat2
        isig2 = scat_op.square(stat2_p_noise-stat2)
        for k in range(1,nsim):
            stat2_p_noise=scat_op.eval(td,image2=imap+noise[k],mask=mask,Auto=False)
            bias2 = bias2 + stat2_p_noise-stat2
            isig2 = isig2 + scat_op.square(stat2_p_noise-stat2)

        bias2=bias2/nsim
        isig2=isig2/nsim-scat_op.square(bias2)
        isig2=1/isig2
        #bias2.reset_P00()

    if rank==2 or size==1:
        #loss3 : dxu = (u+n)xu
        stat3_p_noise=scat_op.eval(i1+noise[0],image2=i2,mask=mask,Auto=True)
        bias3 = stat3_p_noise-stat1
        isig3 = scat_op.square(stat3_p_noise-stat1)
        for k in range(1,nsim):
            stat3_p_noise=scat_op.eval(i1+noise[k],image2=i2,mask=mask,Auto=True)
            bias3 = bias3 + stat3_p_noise-stat1
            isig3 = isig3 + scat_op.square(stat3_p_noise-stat1)

        bias3=bias3/nsim
        isig3=isig3/nsim-scat_op.square(bias3)
        isig3=1/isig3
        #bias3.reset_P00()

    
    if initb1 is None or initb2 is None or initb3 is None :
        if rank==0 or size==1:
            print("BIAS MEAN 0 %f"%(bias1.mean()))
            print("BIAS VAR  0 %f"%(bias1.std()))
        if rank==1 or size==1:
            print("BIAS MEAN 1 %f"%(bias2.mean()))
            print("BIAS VAR  1 %f"%(bias2.std()))
        if rank==2 or size==1:
            print("BIAS MEAN 2 %f"%(bias3.mean()))
            print("BIAS VAR  2 %f"%(bias3.std()))
    else:
        if rank==0 or size==1:
            print("BIAS DVAR 0 %f"%((bias1-initb1).std()))
        if rank==1 or size==1:
            print("BIAS DVAR 1 %f"%((bias2-initb2).std()))
        if rank==2 or size==1:
            print("BIAS DVAR 2 %f"%((bias3-initb3).std()))

    l_outpath=outpath
    
    if rank==0 or size==1:
        initb1=bias1
        bias1.save(l_outpath+'/%s_bias1_%d.npy'%(outname,itt))
        isig1.save(l_outpath+'/%s_isig1_%d.npy'%(outname,itt))
    if rank==1 or size==1:
        initb2=bias2
        bias2.save(l_outpath+'/%s_bias2_%d.npy'%(outname,itt))
        isig2.save(l_outpath+'/%s_isig2_%d.npy'%(outname,itt))
    if rank==2 or size==1:
        initb3=bias3
        bias3.save(l_outpath+'/%s_bias3_%d.npy'%(outname,itt))
        isig3.save(l_outpath+'/%s_isig3_%d.npy'%(outname,itt))
        
    sys.stdout.flush()

    #================================================================
    # BEGIN LEARN BY CONSTRAINING ONLY P00

    if rank==0 or size==1:
        loss1=synthe.Loss(loss_fct1,scat_op,refH-bias1,mask,isig1,True)
    if rank==1 or size==1:
        loss2=synthe.Loss(loss_fct2,scat_op,refX-bias2,td,mask,isig2,True)
    if rank==2 or size==1:
        loss3=synthe.Loss(loss_fct3,scat_op,refH-bias1,di.astype(dtype),bias3,mask,isig3,True)
        loss4=synthe.Loss(loss_fct4,scat_op,di.astype(dtype),sig_noise,Rformat=False)

    if size==1:
        sy = synthe.Synthesis([loss1,loss2,loss3,loss4])
    else:
        if rank==0:
            sy = synthe.Synthesis([loss1])
        if rank==1:
            sy = synthe.Synthesis([loss2])
        if rank==2:
            sy = synthe.Synthesis([loss3,loss4])

    NUM_EPOCHS=100

    omap=sy.run(init_map,
                EVAL_FREQUENCY = 100,
                DECAY_RATE=0.999,
                NUM_EPOCHS = NUM_EPOCHS,
                LEARNING_RATE = 0.3,
                EPSILON = 1E-16)
    
    if docov:
        NUM_EPOCHS=1000+500*itt
    else:
        NUM_EPOCHS=2000+500*itt
    #================================================================
    # START THE REAL RUN
    if rank==0 or size==1:
        loss1=synthe.Loss(loss_fct1,scat_op,refH-bias1,mask,isig1,False)
    if rank==1 or size==1:
        loss2=synthe.Loss(loss_fct2,scat_op,refX-bias2,td,mask,isig2,False)
    if rank==2 or size==1:
        loss3=synthe.Loss(loss_fct3,scat_op,refH-bias1,di.astype(dtype),bias3,mask,isig3,False)
        loss4=synthe.Loss(loss_fct4,scat_op,di.astype(dtype),sig_noise,Rformat=False)

    if size==1:
        sy = synthe.Synthesis([loss1,loss2,loss3,loss4])
    else:
        if rank==0:
            sy = synthe.Synthesis([loss1])
        if rank==1:
            sy = synthe.Synthesis([loss2])
        if rank==2:
            sy = synthe.Synthesis([loss3,loss4])

    omap=sy.run(omap,
                EVAL_FREQUENCY = 100,
                DECAY_RATE=0.999,
                NUM_EPOCHS = NUM_EPOCHS,
                LEARNING_RATE = 0.3,
                EPSILON = 1E-16,
                SHOWGPU=True)

    i1=1*omap
    i2=1*omap
    imap=1*omap
    
    if rank==0:
        # save the intermediate results
        print('ITT %d DONE'%(itt))
        l_outpath=outpath
        sys.stdout.flush()

        sin = scat_op.eval(di,image2=di,mask=mask,Auto=True)
        sout = scat_op.eval(omap,image2=omap,mask=mask,Auto=True)
        
        refH.save(l_outpath+'/%s_cross_%d.npy'%(outname,itt))
        sin.save( l_outpath+'/%s_in_%d.npy'%(outname,itt))
        sout.save(l_outpath+'/%s_out_%d.npy'%(outname,itt))
        np.save(  l_outpath+'%sresult_%d.npy'%(outname,itt),omap/ampmap+off)
            
        np.save(l_outpath+'%slog_%d.npy'%(outname,itt),sy.get_history())

    if test_mpi:
        comm.Barrier()
        
print('Computation Done')
sys.stdout.flush()

