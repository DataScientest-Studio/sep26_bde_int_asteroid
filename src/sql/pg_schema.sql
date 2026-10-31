 DROP TABLE IF EXISTS source_log CASCADE;

CREATE TABLE source_log(
	source_file VARCHAR PRIMARY KEY,
	collection VARCHAR NOT NULL,
	fetched TIMESTAMPTZ NOT NULL,
	params JSONB,
	api_version VARCHAR,
	row_count INT NOT NULL,
	loaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

DROP TABLE IF EXISTS object_dimension CASCADE;

CREATE TABLE object_dimension(
	spkid INT PRIMARY KEY,
	pdes VARCHAR NOT NULL UNIQUE,
	full_name VARCHAR NOT NULL UNIQUE,
	class VARCHAR NOT NULL,
	is_comet BOOLEAN NOT NULL,
	h FLOAT CHECK (h BETWEEN -10 AND 50),
	h_sigma FLOAT,
	diameter FLOAT,
	albedo FLOAT CHECK (albedo > 0 AND albedo <= 2),
	first_seen TIMESTAMPTZ NOT NULL,
	last_seen TIMESTAMPTZ NOT NULL,
	source_file VARCHAR NOT NULL REFERENCES source_log(source_file),
	CHECK (last_seen >= first_seen)
);

DROP TABLE IF EXISTS object_alias CASCADE;

CREATE TABLE object_alias(
	alias_type VARCHAR,
	alias_value VARCHAR,
	spkid INT NOT NULL REFERENCES object_dimension(spkid),
	source_file VARCHAR NOT NULL REFERENCES source_log(source_file),
	PRIMARY KEY(alias_type, alias_value)
);

DROP TABLE IF EXISTS orbit CASCADE;

CREATE TABLE orbit(
	spkid INT REFERENCES object_dimension(spkid),
	orbit_id_num VARCHAR,
	epoch FLOAT NOT NULL,
	epoch_ts TIMESTAMPTZ,
	e FLOAT,
	a FLOAT,
	q FLOAT,
	i FLOAT,
	om FLOAT,
	w FLOAT,
	ma FLOAT,
	n FLOAT,
	per FLOAT,
	moid FLOAT,
	pha BOOLEAN,
	rms FLOAT,
	condition_code INT,
	n_obs_used INT,
	n_del_obs_used INT,
	n_dop_obs_used INT,
	data_arc INT,
	last_obs DATE,
	sigma_a FLOAT,
	sigma_e FLOAT,
	sigma_q FLOAT,
	sigma_i FLOAT,
	sigma_w FLOAT,
	sigma_tp FLOAT,
	valid_from TIMESTAMPTZ  NOT NULL,
	valid_to TIMESTAMPTZ,
	is_current BOOLEAN NOT NULL,
	source_file VARCHAR NOT NULL REFERENCES source_log(source_file),
	CHECK (valid_to IS NULL OR valid_to > valid_from),
	PRIMARY KEY(spkid, orbit_id_num)
);

DROP TABLE IF EXISTS sentry_risk CASCADE;

CREATE TABLE sentry_risk(
	des VARCHAR,
	source_file VARCHAR REFERENCES source_log(source_file),
	spkid INT REFERENCES object_dimension(spkid),
	sentry_id VARCHAR,
	h FLOAT,
	diameter FLOAT,
	v_inf FLOAT,    
	ip FLOAT,      
	ps_cum FLOAT,  
	ps_max FLOAT,
	ts_max INT,
	n_imp INT,   
	last_obs_jd FLOAT,
	last_obs_ts TIMESTAMPTZ,
	range_start INT,
	range_end INT,
	fetched TIMESTAMPTZ  NOT NULL,
	CHECK (range_end >= range_start),
	PRIMARY KEY (des, source_file)
);

DROP TABLE IF EXISTS risk_removal CASCADE;

CREATE TABLE risk_removal(
	des VARCHAR PRIMARY KEY,
	spkid INT REFERENCES object_dimension(spkid),
	removed TIMESTAMPTZ  NOT NULL,
	first_listed TIMESTAMPTZ  NOT NULL,
	source_file VARCHAR NOT NULL REFERENCES source_log(source_file)
);

DROP TABLE IF EXISTS close_approach CASCADE;

CREATE TABLE close_approach(
	des VARCHAR,
	approach_date DATE,
	orbit_id_num VARCHAR,
	spkid INT REFERENCES object_dimension(spkid),
	jd FLOAT NOT NULL,
	jd_raw NUMERIC,
	approach_ts TIMESTAMPTZ  NOT NULL,
	cd_raw VARCHAR,
	dist FLOAT,
	dist_min FLOAT,
	dist_max FLOAT,
	dist_raw NUMERIC,
	dist_min_raw NUMERIC,
	dist_max_raw NUMERIC,
	v_rel FLOAT,
	v_inf FLOAT,
	t_sigma_f VARCHAR,
	source_file VARCHAR NOT NULL REFERENCES source_log(source_file),
	CHECK (dist_min <= dist AND dist <= dist_max),
	PRIMARY KEY(des, approach_date, orbit_id_num)
);


DROP TABLE IF EXISTS risk_change CASCADE;


CREATE TABLE risk_change(
	des VARCHAR,
	fetched TIMESTAMPTZ,
	spkid INT REFERENCES object_dimension(spkid),
	prev_fetched TIMESTAMPTZ  NOT NULL,
	ip_before FLOAT,
	ip_after FLOAT,
	d_ip FLOAT,
	ps_cum_before FLOAT,
	ps_cum_after FLOAT,
	d_ps_cum FLOAT,
	n_imp_before INT,
	n_imp_after INT,
	d_n_imp INT,
	left_sentry BOOLEAN NOT NULL,
	CHECK (fetched > prev_fetched),
	PRIMARY KEY(des, fetched)
);

