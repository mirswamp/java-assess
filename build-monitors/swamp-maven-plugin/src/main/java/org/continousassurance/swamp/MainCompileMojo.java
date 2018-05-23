package org.continousassurance.swamp;

import java.io.File;
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

import org.apache.maven.artifact.DependencyResolutionRequiredException;
import org.apache.maven.project.MavenProject;
import org.codehaus.plexus.util.FileUtils;
import org.continousassurance.swamp.AbstractSwampMojo;


/**
 * Goal which gets package info for swamp.
 *
 * @goal getCompile
 * @phase process-resources
 * @requiresDependencyResolution test
 * @Requiresdirectinvocation true
 * @requiresProject true
 */
public class MainCompileMojo extends AbstractSwampMojo {

	/**
	 * The file encoding to use when reading the source files. If the property <code>project.build.sourceEncoding</code>
	 * is not set, the platform default encoding is used.
	 *
	 * @parameter default-value="${maven.main.skip}"
	 * @readonly
	 */
	boolean skipMainCompile;

	/**
     * <p>
     * Specify where to place generated source files created by annotation processing.
     * Only applies to JDK 1.6+
     * </p>
     * 
     * @parameter( defaultValue = "${project.build.directory}/generated-sources/annotations" )
     * @readonly
	 */
    private File generatedMainSourcesDirectory;

    /**
     * @parameter expression="${swamp.build.monitor.output}" default-value="build_artifacts.xml"
     * @required
     * @readonly
     */
    private String buildMonitorOutputFile;

    /**
     * @parameter expression="${maven.compiler.source}" default-value="1.5"
     * @required
     * @readonly
     */
    private String source;

    /**
     * @parameter expression="${maven.compiler.target}" default-value="1.5"
     * @required
     * @readonly
     */
    private String target;

	/**
	 * @parameter default-value="${project}"
	 * @required
	 * @readonly
	 */
	MavenProject project;

	@Override
	protected MavenProject getProject() {
		return project;
	}
	
	protected File getBuildMonitorOutputFile(){
		return new File(buildMonitorOutputFile);
	}
	
	@Override
	protected boolean skipCompile() {
		boolean skip = false;
		if((getProject().getProperties().getProperty("maven.main.skip", "false").compareToIgnoreCase("true") == 0) ||
				(skipMainCompile == true)) {
			skip = true;
		}
		return skip;
	}

	@Override
	protected File getGeneratedSourcesDirectory() {
		return generatedMainSourcesDirectory;
	}

	@Override
	protected List<File> getSourceDirectories() {
		List<File> src_dirs = new ArrayList<File>();
		
		if(getProject().getCompileSourceRoots() != null) {
			
			for(String dirname : (List<String>)(List<?>)getProject().getCompileSourceRoots()){
				File dir = new File(dirname);
				try {
					if(dir.exists() && (!FileUtils.getFiles(dir, AbstractSwampMojo.ALL_JAVA_PATTERN, null).isEmpty())){
						src_dirs.add(dir);
					}
				} catch (IOException e) {
					e.printStackTrace();
				}
			}
		}
		
		try {
			if (getGeneratedSourcesDirectory() != null && 
					getGeneratedSourcesDirectory().exists() && 
					!FileUtils.getFiles(getGeneratedSourcesDirectory(), AbstractSwampMojo.ALL_JAVA_PATTERN, null).isEmpty()){
				src_dirs.add(getGeneratedSourcesDirectory());
			}
		} catch (IOException e) {
			e.printStackTrace();
		}

		return src_dirs;
	}

	@Override
	protected List<String> getIncludeFileFilters() {
		return getFileFilters(getProject(), "includes", AbstractSwampMojo.ALL_JAVA_PATTERN);
	}

	@Override
	protected List<String> getExcludeFileFilters() {
		return getFileFilters(getProject(), "excludes", "");
	}

	@Override
	protected File getOutputDirectory() {
		return new File(getProject().getBuild().getOutputDirectory());
	}

	@Override
	protected String getSourceVersion() {
		return getPluginParameter("org.apache.maven.plugins:maven-compiler-plugin",
				"source",
				"maven.compiler.source",
				source);
	}

	@Override
	protected String getTargetVersion() {
		return getPluginParameter("org.apache.maven.plugins:maven-compiler-plugin",
				"target",
				"maven.compiler.target",
				target);
	}

	@Override
	protected List<String> getClasspathFiles() throws DependencyResolutionRequiredException {
		return getProject().getCompileClasspathElements();
	}

}
