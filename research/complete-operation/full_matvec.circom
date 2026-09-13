pragma circom 2.1.6;
include "integer_core.circom";
include "node_modules/circomlib/circuits/bitify.circom";
include "node_modules/circomlib/circuits/comparators.circom";

template Signed(B) {
    signal input in;
    signal output magnitude;
    signal output negative;
    signal output encoded;
    component bits = Num2Bits(B);
    bits.in <== in + (1 << (B-1));
    negative <== 1 - bits.out[B-1];
    magnitude <== in * (1 - 2*negative);
    encoded <== in + (1 << (B-1));
}

// n = q*d+r, 0 <= r < d, then round to nearest with ties to even.
// All operands are bounded far below the BN254 modulus.
template RoundPositive(Q, D) {
    signal input n;
    signal input d;
    signal output out;
    signal q;
    signal r;
    q <-- n \ d;
    r <-- n % d;
    component qb = Num2Bits(Q);
    component rb = Num2Bits(D);
    qb.in <== q; rb.in <== r;
    n === q*d+r;
    component rem = LessThan(D);
    rem.in[0] <== r; rem.in[1] <== d; rem.out === 1;
    component gt = LessThan(D+1);
    gt.in[0] <== d; gt.in[1] <== 2*r;
    component eq = IsEqual();
    eq.in[0] <== 2*r; eq.in[1] <== d;
    signal tie;
    tie <== eq.out * qb.out[0];
    out <== q + gt.out + tie;
}

template VectorCommit(N, DOMAIN, B) {
    var PER = 240 \ B;
    var NE = 5 + (N+PER-1) \ PER;
    var NC = NE <= 16 ? 16 : 16+15*((NE-16+14)\15);
    signal input values[N]; // Already range-checked unsigned encodings.
    signal input context;
    signal input index;
    signal input salt;
    signal output out;
    component chain = PoseidonChain(NC);
    chain.in[0] <== DOMAIN;
    chain.in[1] <== context;
    chain.in[2] <== index;
    chain.in[3] <== salt;
    chain.in[4] <== N;
    for(var j=0;j<(N+PER-1)\PER;j++) {
        var acc=0;
        for(var b=0;b<PER;b++) {
            if(j*PER+b<N) acc += values[j*PER+b]*(1 << (B*b));
        }
        chain.in[5+j] <== acc;
    }
    for(var j=NE;j<NC;j++) chain.in[j] <== 0;
    out <== chain.out;
}

template Quantize(K) {
    var NB=K\256;
    signal input x[K];
    signal input inputSalt;
    signal input quantSalt;
    signal input context;
    signal output inputCommitment;
    signal output quantCommitment;
    component xs[K];
    for(var n=0;n<K;n++) {xs[n]=Signed(40);xs[n].in <== x[n];}
    signal maxAbs[NB][257];
    signal maxNeg[NB][257];
    component greater[NB][256];
    component zero[NB];
    component quant[K];
    component scale[NB];
    signal q8[K];
    signal da[NB];
    signal opposite[K];
    for(var b=0;b<NB;b++) {
        maxAbs[b][0] <== 0;maxNeg[b][0] <== 0;
        for(var j=0;j<256;j++) {
            var n=b*256+j;
            greater[b][j]=LessThan(40);
            greater[b][j].in[0] <== maxAbs[b][j]; greater[b][j].in[1] <== xs[n].magnitude;
            maxAbs[b][j+1] <== maxAbs[b][j]+greater[b][j].out*(xs[n].magnitude-maxAbs[b][j]);
            maxNeg[b][j+1] <== maxNeg[b][j]+greater[b][j].out*(xs[n].negative-maxNeg[b][j]);
        }
        zero[b]=IsZero();zero[b].in <== maxAbs[b][256];
        scale[b]=RoundPositive(34,8);
        scale[b].n <== maxAbs[b][256];scale[b].d <== 127;
        da[b] <== scale[b].out*(2*maxNeg[b][256]-1);
        for(var j=0;j<256;j++) {
            var n=b*256+j;
            quant[n]=RoundPositive(8,40);
            quant[n].n <== 127*xs[n].magnitude;
            quant[n].d <== maxAbs[b][256]+zero[b].out;
            opposite[n] <== xs[n].negative+maxNeg[b][256]-2*xs[n].negative*maxNeg[b][256];
            q8[n] <== quant[n].out*(2*opposite[n]-1);
        }
    }
    component xc=VectorCommit(K,3002,40);
    xc.context <== context;xc.index <== 0;xc.salt <== inputSalt;
    for(var n=0;n<K;n++)xc.values[n] <== xs[n].encoded;
    inputCommitment <== xc.out;
    component qc=VectorCommit(K+NB,3004,40);
    qc.context <== context;qc.index <== 0;qc.salt <== quantSalt;
    for(var n=0;n<K;n++)qc.values[n] <== q8[n]+(1 << 39);
    for(var n=0;n<NB;n++)qc.values[K+n] <== da[n]+(1 << 39);
    quantCommitment <== qc.out;
}

template CompleteRows(ROWS,K) {
    var NB=K\256;
    signal input q8[K];
    signal input da[NB];
    signal input y[ROWS];
    signal input q4bits[ROWS*K*4];
    signal input scbits[ROWS*NB*8*6];
    signal input mnbits[ROWS*NB*8*6];
    signal input D[ROWS*NB];
    signal input Dmin[ROWS*NB];
    signal input s1[ROWS*NB];
    signal input s2[ROWS*NB];
    signal input quantSalt;
    signal input outputSalt;
    signal input context;
    signal input group;
    signal output weightCommitment;
    signal output quantCommitment;
    signal output outputCommitment;
    component groupBits=Num2Bits(32); groupBits.in <== group;
    component dot=QDotRows(ROWS,K);
    dot.salt <== 0;
    for(var n=0;n<ROWS*K*4;n++)dot.q4bits[n] <== q4bits[n];
    for(var n=0;n<ROWS*NB*8*6;n++){dot.scbits[n] <== scbits[n];dot.mnbits[n] <== mnbits[n];}
    for(var n=0;n<K;n++)dot.q8[n] <== q8[n];
    component ds[ROWS*NB];component dms[ROWS*NB];
    signal term1[ROWS*NB];signal term2[ROWS*NB];signal term[ROWS*NB];
    component accSigned[ROWS];component rounding[ROWS];component ys[ROWS];
    for(var row=0;row<ROWS;row++) {
        var acc=0;
        for(var b=0;b<NB;b++) {
            var n=row*NB+b;
            dot.s1[n] <== s1[n];dot.s2[n] <== s2[n];
            ds[n]=Signed(41);ds[n].in <== D[n];
            dms[n]=Signed(41);dms[n].in <== Dmin[n];
            term1[n] <== D[n]*s1[n];term2[n] <== Dmin[n]*s2[n];
            term[n] <== da[b]*(term1[n]-term2[n]);
            acc += term[n];
        }
        accSigned[row]=Signed(104);accSigned[row].in <== acc;
        rounding[row]=RoundPositive(80,25);
        rounding[row].n <== accSigned[row].magnitude;rounding[row].d <== (1 << 24);
        y[row] === rounding[row].out*(1-2*accSigned[row].negative);
        ys[row]=Signed(40);ys[row].in <== y[row];
    }
    component wc=VectorCommit(ROWS*NB*2,3001,41);
    wc.context <== 0;wc.index <== 0;wc.salt <== 0;
    for(var n=0;n<ROWS*NB;n++) {wc.values[n] <== ds[n].encoded;wc.values[ROWS*NB+n] <== dms[n].encoded;}
    component weights=Poseidon(4);
    weights.inputs[0] <== dot.commitment;weights.inputs[1] <== wc.out;
    weights.inputs[2] <== ROWS;weights.inputs[3] <== K;
    weightCommitment <== weights.out;
    component qs[K];component nonMin[K];component das[NB];
    component qc=VectorCommit(K+NB,3004,40);
    qc.context <== context;qc.index <== 0;qc.salt <== quantSalt;
    for(var n=0;n<K;n++) {
        qs[n]=Signed(8);qs[n].in <== q8[n];
        nonMin[n]=IsZero();nonMin[n].in <== qs[n].encoded;nonMin[n].out === 0;
        qc.values[n] <== q8[n]+(1 << 39);
    }
    for(var n=0;n<NB;n++) {
        das[n]=Signed(34);das[n].in <== da[n];
        qc.values[K+n] <== da[n]+(1 << 39);
    }
    quantCommitment <== qc.out;
    component yc=VectorCommit(ROWS,3003,40);
    yc.context <== context;yc.index <== group;yc.salt <== outputSalt;
    for(var n=0;n<ROWS;n++)yc.values[n] <== ys[n].encoded;
    outputCommitment <== yc.out;
}
