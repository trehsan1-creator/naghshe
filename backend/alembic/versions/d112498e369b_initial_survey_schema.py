"""initial survey schema

Revision ID: d112498e369b
Revises: 
Create Date: 2026-11-04 07:39:31.482148
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
import geoalchemy2


revision = 'd112498e369b'
down_revision = None
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if _is_postgres():
        # PostGIS must exist before a POINTZ column can be created on PostgreSQL.
        op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    op.create_table('projects',
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('code', sa.String(length=64), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('client', sa.String(length=200), nullable=True),
    sa.Column('location', sa.String(length=200), nullable=True),
    sa.Column('surveyor', sa.String(length=200), nullable=True),
    sa.Column('crs_epsg', sa.Integer(), nullable=False),
    sa.Column('vertical_datum', sa.String(length=32), nullable=False),
    sa.Column('linear_unit', sa.String(length=16), nullable=False),
    sa.Column('angle_unit', sa.String(length=16), nullable=False),
    sa.Column('duplicate_xy_tolerance', sa.Float(), nullable=False),
    sa.Column('duplicate_z_tolerance', sa.Float(), nullable=False),
    sa.Column('z_mad_threshold', sa.Float(), nullable=False),
    sa.Column('local_z_step_threshold', sa.Float(), nullable=False),
    sa.Column('tin_boundary_mode', sa.String(length=24), nullable=False),
    sa.Column('contour_interval', sa.Float(), nullable=False),
    sa.Column('breakline_codes', sa.JSON(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('dependency_state', sa.String(length=16), nullable=False),
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_projects'))
    )
    op.create_index(op.f('ix_projects_code'), 'projects', ['code'], unique=False)
    op.create_index(op.f('ix_projects_name'), 'projects', ['name'], unique=False)
    op.create_index(op.f('ix_projects_status'), 'projects', ['status'], unique=False)
    op.create_table('code_mappings',
    sa.Column('project_id', sa.String(length=32), nullable=False),
    sa.Column('code', sa.String(length=32), nullable=False),
    sa.Column('kind', sa.String(length=16), nullable=False),
    sa.Column('layer', sa.String(length=64), nullable=False),
    sa.Column('block_name', sa.String(length=64), nullable=True),
    sa.Column('color', sa.Integer(), nullable=False),
    sa.Column('description', sa.String(length=200), nullable=True),
    sa.Column('is_breakline', sa.Boolean(), nullable=False),
    sa.Column('enabled', sa.Boolean(), nullable=False),
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_code_mappings_project_id_projects'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_code_mappings')),
    sa.UniqueConstraint('project_id', 'code', name='uq_code_project_code')
    )
    op.create_index(op.f('ix_code_mappings_project_id'), 'code_mappings', ['project_id'], unique=False)
    op.create_table('derived_outputs',
    sa.Column('project_id', sa.String(length=32), nullable=False),
    sa.Column('kind', sa.String(length=24), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('params', sa.JSON(), nullable=True),
    sa.Column('summary', sa.JSON(), nullable=True),
    sa.Column('payload_path', sa.Text(), nullable=True),
    sa.Column('payload_inline', sa.JSON(), nullable=True),
    sa.Column('source_hash', sa.String(length=64), nullable=True),
    sa.Column('source_point_count', sa.Integer(), nullable=False),
    sa.Column('depends_on', sa.JSON(), nullable=True),
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_derived_outputs_project_id_projects'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_derived_outputs'))
    )
    op.create_index(op.f('ix_derived_outputs_kind'), 'derived_outputs', ['kind'], unique=False)
    op.create_index(op.f('ix_derived_outputs_project_id'), 'derived_outputs', ['project_id'], unique=False)
    op.create_index(op.f('ix_derived_outputs_source_hash'), 'derived_outputs', ['source_hash'], unique=False)
    op.create_index(op.f('ix_derived_outputs_status'), 'derived_outputs', ['status'], unique=False)
    op.create_table('layer_standards',
    sa.Column('project_id', sa.String(length=32), nullable=False),
    sa.Column('name', sa.String(length=64), nullable=False),
    sa.Column('color', sa.Integer(), nullable=False),
    sa.Column('linetype', sa.String(length=32), nullable=False),
    sa.Column('description', sa.String(length=200), nullable=True),
    sa.Column('visible', sa.Boolean(), nullable=False),
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_layer_standards_project_id_projects'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_layer_standards')),
    sa.UniqueConstraint('project_id', 'name', name='uq_layer_project_name')
    )
    op.create_index(op.f('ix_layer_standards_project_id'), 'layer_standards', ['project_id'], unique=False)
    op.create_table('project_files',
    sa.Column('project_id', sa.String(length=32), nullable=False),
    sa.Column('original_filename', sa.String(length=255), nullable=False),
    sa.Column('stored_filename', sa.String(length=255), nullable=False),
    sa.Column('storage_path', sa.Text(), nullable=False),
    sa.Column('sha256', sa.String(length=64), nullable=False),
    sa.Column('size_bytes', sa.Integer(), nullable=False),
    sa.Column('file_format', sa.String(length=16), nullable=False),
    sa.Column('encoding', sa.String(length=32), nullable=True),
    sa.Column('delimiter', sa.String(length=8), nullable=True),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('row_count', sa.Integer(), nullable=False),
    sa.Column('imported_points', sa.Integer(), nullable=False),
    sa.Column('import_log', sa.JSON(), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_project_files_project_id_projects'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_project_files'))
    )
    op.create_index(op.f('ix_project_files_file_format'), 'project_files', ['file_format'], unique=False)
    op.create_index(op.f('ix_project_files_project_id'), 'project_files', ['project_id'], unique=False)
    op.create_index(op.f('ix_project_files_sha256'), 'project_files', ['sha256'], unique=False)
    op.create_index(op.f('ix_project_files_status'), 'project_files', ['status'], unique=False)
    op.create_table('survey_points',
    sa.Column('project_id', sa.String(length=32), nullable=False),
    sa.Column('file_id', sa.String(length=32), nullable=True),
    sa.Column('point_number', sa.String(length=64), nullable=False),
    sa.Column('easting', sa.Float(), nullable=False),
    sa.Column('northing', sa.Float(), nullable=False),
    sa.Column('elevation', sa.Float(), nullable=True),
    sa.Column('code', sa.String(length=64), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('layer', sa.String(length=64), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('source_order', sa.Integer(), nullable=False),
    sa.Column('line_no', sa.Integer(), nullable=True),
    sa.Column('qa_severity', sa.String(length=16), nullable=True),
    sa.Column('qa_flags', sa.Text(), nullable=True),
    sa.Column('geom', sa.Text().with_variant(geoalchemy2.types.Geometry(geometry_type='POINTZ', srid=0, dimension=3, from_text='ST_GeomFromEWKT', name='geometry'), 'postgresql'), nullable=True),
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['file_id'], ['project_files.id'], name=op.f('fk_survey_points_file_id_project_files'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_survey_points_project_id_projects'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_survey_points'))
    )
    op.create_index(op.f('ix_survey_points_code'), 'survey_points', ['code'], unique=False)
    op.create_index(op.f('ix_survey_points_easting'), 'survey_points', ['easting'], unique=False)
    op.create_index(op.f('ix_survey_points_elevation'), 'survey_points', ['elevation'], unique=False)
    op.create_index(op.f('ix_survey_points_layer'), 'survey_points', ['layer'], unique=False)
    op.create_index(op.f('ix_survey_points_northing'), 'survey_points', ['northing'], unique=False)
    op.create_index(op.f('ix_survey_points_point_number'), 'survey_points', ['point_number'], unique=False)
    op.create_index(op.f('ix_survey_points_project_id'), 'survey_points', ['project_id'], unique=False)
    op.create_index(op.f('ix_survey_points_qa_severity'), 'survey_points', ['qa_severity'], unique=False)
    op.create_index(op.f('ix_survey_points_status'), 'survey_points', ['status'], unique=False)
    op.create_table('survey_stations',
    sa.Column('project_id', sa.String(length=32), nullable=False),
    sa.Column('file_id', sa.String(length=32), nullable=True),
    sa.Column('point_number', sa.String(length=64), nullable=False),
    sa.Column('easting', sa.Float(), nullable=True),
    sa.Column('northing', sa.Float(), nullable=True),
    sa.Column('elevation', sa.Float(), nullable=True),
    sa.Column('instrument_height', sa.Float(), nullable=False),
    sa.Column('reflector_height', sa.Float(), nullable=True),
    sa.Column('orientation_rad', sa.Float(), nullable=True),
    sa.Column('orientation_source', sa.String(length=32), nullable=True),
    sa.Column('line_no', sa.Integer(), nullable=True),
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['file_id'], ['project_files.id'], name=op.f('fk_survey_stations_file_id_project_files'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_survey_stations_project_id_projects'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_survey_stations'))
    )
    op.create_index(op.f('ix_survey_stations_point_number'), 'survey_stations', ['point_number'], unique=False)
    op.create_index(op.f('ix_survey_stations_project_id'), 'survey_stations', ['project_id'], unique=False)
    op.create_table('raw_observations',
    sa.Column('project_id', sa.String(length=32), nullable=False),
    sa.Column('file_id', sa.String(length=32), nullable=True),
    sa.Column('station_id', sa.String(length=32), nullable=True),
    sa.Column('point_number', sa.String(length=64), nullable=False),
    sa.Column('line_no', sa.Integer(), nullable=True),
    sa.Column('hz_rad', sa.Float(), nullable=True),
    sa.Column('v_rad', sa.Float(), nullable=True),
    sa.Column('slope_distance', sa.Float(), nullable=True),
    sa.Column('horizontal_distance', sa.Float(), nullable=True),
    sa.Column('height_difference', sa.Float(), nullable=True),
    sa.Column('reflector_height', sa.Float(), nullable=True),
    sa.Column('code', sa.String(length=64), nullable=True),
    sa.Column('description', sa.String(length=255), nullable=True),
    sa.Column('face', sa.String(length=4), nullable=False),
    sa.Column('computed_easting', sa.Float(), nullable=True),
    sa.Column('computed_northing', sa.Float(), nullable=True),
    sa.Column('computed_elevation', sa.Float(), nullable=True),
    sa.Column('recorded_easting', sa.Float(), nullable=True),
    sa.Column('recorded_northing', sa.Float(), nullable=True),
    sa.Column('recorded_elevation', sa.Float(), nullable=True),
    sa.Column('id', sa.String(length=32), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
    sa.ForeignKeyConstraint(['file_id'], ['project_files.id'], name=op.f('fk_raw_observations_file_id_project_files'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_raw_observations_project_id_projects'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['station_id'], ['survey_stations.id'], name=op.f('fk_raw_observations_station_id_survey_stations'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_raw_observations'))
    )
    op.create_index(op.f('ix_raw_observations_point_number'), 'raw_observations', ['point_number'], unique=False)
    op.create_index(op.f('ix_raw_observations_project_id'), 'raw_observations', ['project_id'], unique=False)
    op.create_index(op.f('ix_raw_observations_station_id'), 'raw_observations', ['station_id'], unique=False)
    if _is_postgres():
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_survey_points_geom "
            "ON survey_points USING GIST (geom)"
        )


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f('ix_raw_observations_station_id'), table_name='raw_observations')
    op.drop_index(op.f('ix_raw_observations_project_id'), table_name='raw_observations')
    op.drop_index(op.f('ix_raw_observations_point_number'), table_name='raw_observations')
    op.drop_table('raw_observations')
    op.drop_index(op.f('ix_survey_stations_project_id'), table_name='survey_stations')
    op.drop_index(op.f('ix_survey_stations_point_number'), table_name='survey_stations')
    op.drop_table('survey_stations')
    op.drop_index(op.f('ix_survey_points_status'), table_name='survey_points')
    op.drop_index(op.f('ix_survey_points_qa_severity'), table_name='survey_points')
    op.drop_index(op.f('ix_survey_points_project_id'), table_name='survey_points')
    op.drop_index(op.f('ix_survey_points_point_number'), table_name='survey_points')
    op.drop_index(op.f('ix_survey_points_northing'), table_name='survey_points')
    op.drop_index(op.f('ix_survey_points_layer'), table_name='survey_points')
    op.drop_index(op.f('ix_survey_points_elevation'), table_name='survey_points')
    op.drop_index(op.f('ix_survey_points_easting'), table_name='survey_points')
    op.drop_index(op.f('ix_survey_points_code'), table_name='survey_points')
    op.drop_table('survey_points')
    op.drop_index(op.f('ix_project_files_status'), table_name='project_files')
    op.drop_index(op.f('ix_project_files_sha256'), table_name='project_files')
    op.drop_index(op.f('ix_project_files_project_id'), table_name='project_files')
    op.drop_index(op.f('ix_project_files_file_format'), table_name='project_files')
    op.drop_table('project_files')
    op.drop_index(op.f('ix_layer_standards_project_id'), table_name='layer_standards')
    op.drop_table('layer_standards')
    op.drop_index(op.f('ix_derived_outputs_status'), table_name='derived_outputs')
    op.drop_index(op.f('ix_derived_outputs_source_hash'), table_name='derived_outputs')
    op.drop_index(op.f('ix_derived_outputs_project_id'), table_name='derived_outputs')
    op.drop_index(op.f('ix_derived_outputs_kind'), table_name='derived_outputs')
    op.drop_table('derived_outputs')
    op.drop_index(op.f('ix_code_mappings_project_id'), table_name='code_mappings')
    op.drop_table('code_mappings')
    op.drop_index(op.f('ix_projects_status'), table_name='projects')
    op.drop_index(op.f('ix_projects_name'), table_name='projects')
    op.drop_index(op.f('ix_projects_code'), table_name='projects')
    op.drop_table('projects')
    # ### end Alembic commands ###
