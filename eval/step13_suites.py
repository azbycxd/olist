"""One-command suite entrypoint, with the same rehearsal/registration/run gates."""
import argparse
import json

from eval.step13_errors import ROOT,read


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('suite',choices=['regression','capability'])
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--rehearsal',action='store_true')
    mode.add_argument('--register',action='store_true')
    mode.add_argument('--run',action='store_true')
    args=parser.parse_args()
    if args.rehearsal or args.run:
        from eval.step13_run import run
        run(args.suite,rehearsal=args.rehearsal)
    elif args.register:
        from eval.step13_trials import register
        register(args.suite)
    else:
        cases=read(ROOT/f'eval/step13_{args.suite}_cases.json')
        print(json.dumps({'suite':args.suite,'questions':[q['id'] for q in cases],
            'note':'List only. --rehearsal runs HTTP doubles; --register writes a protocol; commit/push it before --run. Existing real-run markers prohibit reruns.'},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
