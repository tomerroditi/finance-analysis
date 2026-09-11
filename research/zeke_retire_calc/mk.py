import sys
sys.path.insert(0,'.')
import probe

def erow(i, sum_, st, ed, sd="", edt="", rise="0.0"):
    return {f"expenseStartType{i}": st, f"expenseStartDate{i}": sd,
            f"expenseEndType{i}": ed, f"expenseEndDate{i}": edt,
            f"expenseSum{i}": str(sum_), f"expenseRise{i}": rise,
            f"expenseDescription{i}": f"e{i}"}

def irow(i, sum_, st, ed, sd="", edt="", rise="0.0"):
    return {f"incomeStartType{i}": st, f"incomeStartDate{i}": sd,
            f"incomeEndType{i}": ed, f"incomeEndDate{i}": edt,
            f"incomeSum{i}": str(sum_), f"incomeRise{i}": rise,
            f"incomeDescription{i}": f"i{i}"}

def build(erows, irows, **extra):
    ov = dict(probe.BASE)
    ov["num_expense_fields"] = str(1+len(erows))
    ov["num_income_fields"] = str(1+len(irows))
    for r in erows: ov.update(r)
    for r in irows: ov.update(r)
    ov.update({k:str(v) for k,v in extra.items()})
    return ov
