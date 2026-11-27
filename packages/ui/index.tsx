export function Mark(){return <span className="mark" aria-hidden="true"><i/><i/><i/><i/><i/></span>}
export function Button({children,className="",...props}:React.ButtonHTMLAttributes<HTMLButtonElement>){return <button className={"button "+className} {...props}>{children}</button>}
export function Section({title,detail,children}:{title:string;detail?:string;children:React.ReactNode}){return <section className="panel"><div className="section-head"><h2>{title}</h2>{detail&&<p>{detail}</p>}</div>{children}</section>}
