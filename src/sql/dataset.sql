select
    dim.spkid,
    dim.pdes,
    case when dim.spkid in (select spkid from risk_removal where spkid is not null)
           or dim.spkid in (select a.spkid from object_alias a join risk_removal r on r.des = a.alias_value)
         then 1 else 0
    end as removed,
    o.moid,
    o.q,
    o.a,
    o.e,
    o.i,
    o.om,
    o.w,
    dim.h,
    dim.h_sigma,
    (dim.h_sigma is not null) as has_h_sigma,
    (dim.diameter is not null) as has_diameter,
    coalesce(o.n_obs_used, 0) as n_obs_used,
    coalesce(o.n_del_obs_used, 0) as n_del_obs_used,
    coalesce(o.n_dop_obs_used, 0) as n_dop_obs_used,
    (coalesce(o.n_del_obs_used, 0) + coalesce(o.n_dop_obs_used, 0) > 0) as has_radar,
    coalesce(o.data_arc, 0) as data_arc,
    current_date - o.last_obs as days_since_last_obs,
    o.rms,
    o.condition_code,
    o.sigma_a,
    o.sigma_e,
    o.sigma_q,
    o.sigma_i,
    o.sigma_w,
    o.sigma_tp,
    dim.class
from object_dimension dim
left join orbit o
    on o.spkid = dim.spkid
   and o.is_current = true
where o.spkid is not null
  and (dim.spkid in (select spkid from sentry_risk where spkid is not null)
       or dim.spkid in (select spkid from risk_removal where spkid is not null)
       or dim.spkid in (select a.spkid from object_alias a join risk_removal r on r.des = a.alias_value))
order by dim.spkid;
