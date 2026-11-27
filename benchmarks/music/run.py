"""Run from repo root: python -m benchmarks.music.run --output /tmp/synora-bench"""
import argparse
from dataclasses import asdict
from pathlib import Path
import hashlib
import json
import math
import platform
import time
from engines.music import MusicSpec, GenerationContext, registry, MusicError

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider",action="append")
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--case",action="append")
    parser.add_argument("--repeats",type=int,default=1,choices=range(1,6))
    parser.add_argument("--seed",type=int,default=42)
    parser.add_argument("--budget-usd",type=float,default=0)
    parser.add_argument("--allow-real",action="store_true")
    args=parser.parse_args()
    if not math.isfinite(args.budget_usd) or args.budget_usd<0 or not 0<=args.seed<=2147483643:
        parser.error("invalid budget or seed")
    providers=registry()
    names=args.provider or ["fixture"]
    if any(p not in providers for p in names):
        parser.error("provider unavailable; check explicit approval and configuration")
    prompt_file=Path(__file__).with_name("prompts.json")
    raw=prompt_file.read_bytes()
    cases=json.loads(raw)
    if args.case:
        cases=[c for c in cases if c["id"] in args.case]
        if set(args.case)!={c["id"] for c in cases}:
            parser.error("unknown case")
    reservations=sum(getattr(providers[n],"cost",0)*args.repeats*len(cases) for n in names)
    if any(not providers[n].capabilities.simulated for n in names) and (not args.allow_real or reservations>args.budget_usd):
        parser.error("approved total budget insufficient for all requested calls")
    args.output.mkdir(parents=True,exist_ok=False)
    manifest={"prompt_sha256":hashlib.sha256(raw).hexdigest(),"python":platform.python_version(),
              "platform":platform.platform(),"repeats":args.repeats,"seed":args.seed,
              "maximum_estimated_reservations_usd":reservations,
              "providers":{n:asdict(providers[n].capabilities) for n in names}}
    (args.output/"manifest.json").write_text(json.dumps(manifest,indent=2))
    failures=0
    with (args.output/"results.jsonl").open("x",encoding="utf-8") as f:
        for name in names:
            provider=providers[name]
            for case in cases:
                spec=MusicSpec(**{k:v for k,v in case.items() if k!="id"})
                for repeat in range(args.repeats):
                    seed=args.seed+repeat
                    row={"provider":name,"case":case["id"],"repeat":repeat,"seed":seed,
                         "simulated":provider.capabilities.simulated,"requested_duration_seconds":spec.duration_seconds,
                         "quality_score":None,"prompt_adherence_score":None,"gpu_peak_vram_bytes":None,
                         "remote_compute_seconds":None,"actual_cost_usd":None}
                    start=time.perf_counter()
                    cpu_start=time.process_time()
                    try:
                        provider.capabilities.validate(spec)
                    except MusicError as e:
                        row.update(status="unsupported",error=str(e))
                    else:
                        try:
                            out=provider.generate(spec,GenerationContext(
                                args.output/name/case["id"]/str(repeat),seed=seed,
                                allow_real=args.allow_real,budget_usd=getattr(provider,"cost",0)))
                            row.update(status="succeeded",artifact=str(out.artifact.relative_to(args.output)),
                                       metrics=out.metrics,provenance=out.provenance,model=out.model,revision=out.revision,
                                       duration_error_seconds=abs(out.actual_duration_seconds-spec.duration_seconds),
                                       estimated_cost_usd=out.estimated_cost_usd)
                        except Exception as e:
                            # Do not print arbitrary exception strings (could include credentials).
                            row.update(status="failed",error=str(e) if isinstance(e,MusicError) else type(e).__name__)
                            failures+=1
                    row["latency_seconds"]=time.perf_counter()-start
                    row["client_cpu_seconds"]=time.process_time()-cpu_start
                    f.write(json.dumps(row,ensure_ascii=False)+"\n")
                    f.flush()
                    print(name,case["id"],repeat,row["status"],flush=True)
    return int(failures>0)

if __name__=="__main__":
    raise SystemExit(main())
