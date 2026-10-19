"""Report calculations for probit analyses.

The original uses a heterogeneity-adjusted Fieller interval for log-dose MLE,
rounded critical-value tables, and a symmetric finite-difference dose error.
See docs/help-advanced-audit.json for native evidence and reference tests.
"""
import numpy as np
from scipy import stats
from . import advanced as a

PERCENTILES=np.array([1,5,10,16,20,25,30,40,50,60,70,75,80,84,90,95,99])/100
_CHI95=np.array([3.84,5.99,7.81,9.49,11.07,12.59,14.07,15.51,16.92,18.31,19.68,21.,22.4,23.7,25.,26.3,27.59,28.87,30.14,31.41,32.67,33.92,35.17,36.42])
_T975=np.array([12.706,4.303,3.182,2.776,2.571,2.447,2.365,2.306,2.262,2.228,2.201,2.179,2.16,2.145,2.131,2.12,2.11,2.101,2.093,2.086,2.08,2.074,2.069,2.064])


def critical_values(df):
    index=df-1
    if index<0:return 0.,0.
    if index<24:return _CHI95[index],_T975[index]
    return (index-24)*1.2+37.65,2.683/index+1.952


def append(r,label,mode,dose,x,events,total,adjusted,probits,coef,ls_weights=None):
    linear=coef[0]+coef[1]*x;probability=stats.norm.cdf(linear-5);expected=total*probability
    if mode==0:
        weight=total*stats.norm.pdf(linear-5)**2/(probability*(1-probability))
        chisquare=np.sum((events-expected)**2/(total*probability*(1-probability)))
    else:
        weight=ls_weights;chisquare=np.sum(weight*(probits-linear)**2)
    df=len(x)-2;threshold,critical=critical_values(df)
    scale=chisquare/df if chisquare>=threshold else 1.
    if chisquare<threshold:critical=1.96
    r['tables'].append(a._table(label+' goodness of fit',['Chi-square','df','p','Heterogeneity scale','Interval critical value'],[[chisquare,df,stats.chi2.sf(chisquare,df),scale,critical]]))
    r['tables'].append(a._table(label+' observed and expected',['Dose','Log10 dose' if mode==0 else 'Dose predictor','Adjusted probability','Fitted probability','Sample size','Adjusted observed count','Expected count','Difference'],zip(dose,x,adjusted,probability,total,adjusted*total,expected,adjusted*total-expected)))
    if abs(coef[1])<=1e-15:return
    probabilities=PERCENTILES if mode==0 else np.array([.1,stats.norm.cdf(-1),.5,stats.norm.cdf(1),.9])
    inverse=(5+stats.norm.ppf(probabilities)-coef[0])/coef[1]
    if mode==0:
        sumweight=weight.sum();mean=np.average(x,weights=weight);spread=np.dot(weight,(x-mean)**2)
        g=scale*critical**2/(coef[1]**2*spread)
        if g<1:
            error=np.sqrt(np.abs(scale*((1-g)/sumweight+(inverse-mean)**2/spread)))/(coef[1]*(1-g))
            center=inverse+g/(1-g)*(inverse-mean)
        else:
            error=np.sqrt(scale*(1/sumweight+(inverse-mean)**2/spread)/coef[1]**2)
            center=inverse
            r['warnings'].append(label+': the native inverse-dose interval falls back to its delta formula when the Fieller g factor is at least one.')
        with np.errstate(over='ignore',invalid='ignore'):
            dose_estimate=10.**inverse;dose_error=(10.**(inverse+error)-10.**(inverse-error))/2
            lower=10.**(center-critical*error);upper=10.**(center+critical*error)
        rows=zip(probabilities,dose_estimate,5+stats.norm.ppf(probabilities),inverse,error,dose_error,lower,upper)
        r['tables'].append(a._table(label+' effective dose',['Response probability','Dose','Probit','Log10 dose','Log10 dose standard error','Dose standard error','Lower dose','Upper dose'],rows))
    else:
        central=total[(probits>3.5)&(probits<6.5)].sum()
        error=(inverse[3]-inverse[1])/np.sqrt(2*central) if central>0 else np.nan
        critical=stats.t.isf(.025,int(central)-1) if central>1 else np.nan
        r['tables'].append(a._table(label+' effective dose',['Response probability','Dose','Probit'],zip(probabilities,inverse,5+stats.norm.ppf(probabilities))))
        r['tables'].append(a._table(label+' LD50 precision',['LD50','Standard error','Lower dose','Upper dose','Central-range total N'],[[inverse[2],error,inverse[2]-critical*error,inverse[2]+critical*error,central]]))
    r['notes'].append(label+(': inverse-dose intervals use a fixed 95% critical value and heterogeneity adjustment; the dose standard error is half the distance between back-transformed log-dose ± one standard error.' if mode==0 else ': LD50 standard error uses (LD84−LD16)/√(2N), with N restricted to the central probit range (3.5,6.5).'))
