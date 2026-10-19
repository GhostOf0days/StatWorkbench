"""Independent quadrature implementation of the observed native range probability."""
import math
from functools import cmp_to_key


def ordered_groups(groups):
    def compare(left,right):
        a,b=str(left[0]).strip(),str(right[0]).strip()
        try:
            x,y=float(a),float(b)
            if math.isfinite(x) and math.isfinite(y):return (x>y)-(x<y)
        except ValueError:pass
        return (a>b)-(a<b)
    return sorted(groups,key=cmp_to_key(compare))


def range_survival(q, groups, df):
    """Finite quadrature with fixed integration tolerances."""
    if df<1 or groups<2:raise ValueError('Studentized range requires df >= 1 and at least two groups.')
    if math.isnan(q):return math.nan
    if q<=0:return 1.0
    if math.isinf(q):return 0.0
    step=.45*groups**(-.2)
    center=.5*math.log(groups)
    exponent=groups-1
    h=.45/math.sqrt(df)
    half_df=df/2
    coefficient={1:.193064705,2:.293525326}.get(df)
    if coefficient is None:
        coefficient=math.sqrt(half_df)*.318309886/(1+((-.00268132716/half_df+.00347222222)/half_df+.0833333333)/half_df)
    log_weight=math.log(coefficient*groups*step*h)
    sf=lambda x:.5*math.erfc(x/math.sqrt(2))
    def integrand(base,delta):
        return math.exp(base+exponent*math.log(delta)) if delta>0 else 0.0
    total=0.0;previous=1.0;before_previous=1.0;offset=step
    for ring in range(15):
        offset-=step
        while True:
            offset=-offset
            value=0.0
            if before_previous>1e-4 or ring+1<8:
                point=center+offset;base=log_weight-point*point/2;tail=sf(point)
                value=integrand(base,sf(point-q)-tail)
                if df<=120:
                    for sign in (1,-1):
                        for j in range(1,14):
                            log_scale=sign*h*j;scale=math.exp(log_scale)
                            log_density=df*(log_scale+.5-scale*scale/2)
                            term=integrand(base+log_density,sf(point-q*scale)-tail)
                            value+=term
                            require_minimum=sign==1 and j<4 and ring+1<8
                            if term<=3e-5 and not require_minimum:break
            total+=value
            if ring+1>7 and value<=1e-4 and previous<=1e-4:break
            before_previous,previous=previous,value
            if offset<=0:break
    return 1-total
