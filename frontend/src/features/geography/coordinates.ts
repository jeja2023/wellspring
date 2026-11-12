import transform from 'coordtransform'
export type CoordinateSystem = 'WGS84'|'GCJ02'
export type Position = [longitude:number,latitude:number]
export type Bounds = [west:number,south:number,east:number,north:number]

/** Offline approximate display conversion. Stored business coordinates remain WGS84. */
export function toMap(position:Position,system:CoordinateSystem):Position {
  return system==='GCJ02'?transform.wgs84togcj02(...position):[...position]
}

/** Refine the inverse against the same approximate forward model, not survey accuracy. */
export function fromMap(position:Position,system:CoordinateSystem):Position {
  if(system==='WGS84')return [...position]
  let estimate=transform.gcj02towgs84(...position)
  for(let iteration=0;iteration<8;iteration++){
    const mapped=transform.wgs84togcj02(...estimate)
    const dx=mapped[0]-position[0],dy=mapped[1]-position[1]
    estimate=[estimate[0]-dx,estimate[1]-dy]
    if(Math.max(Math.abs(dx),Math.abs(dy))<1e-9)break
  }
  return estimate
}

/** Sample the nonlinear viewport edges and retain a small conservative query margin. */
export function toWgsBounds(bounds:Bounds,system:CoordinateSystem):Bounds {
  if(system==='WGS84')return [...bounds]
  const [west,south,east,north]=bounds,positions:Position[]=[]
  for(let step=0;step<=16;step++){
    const longitude=west+(east-west)*step/16,latitude=south+(north-south)*step/16
    positions.push(fromMap([longitude,south],system),fromMap([longitude,north],system),fromMap([west,latitude],system),fromMap([east,latitude],system))
  }
  const longitudes=positions.map(row=>row[0]),latitudes=positions.map(row=>row[1]),margin=0.0001
  return [Math.max(-180,Math.min(...longitudes)-margin),Math.max(-85,Math.min(...latitudes)-margin),
    Math.min(180,Math.max(...longitudes)+margin),Math.min(85,Math.max(...latitudes)+margin)]
}
